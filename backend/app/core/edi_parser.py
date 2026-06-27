from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


class EDIParseError(ValueError):
    """Raised when an EDIFACT COEDOR payload cannot be parsed."""


@dataclass(slots=True)
class ParsedContainer:
    container_number: str
    iso_type_code: str | None = None
    gross_weight_kg: float | None = None
    tare_weight_kg: float | None = None
    payload_weight_kg: float | None = None
    bay: int | None = None
    row: int | None = None
    tier: int | None = None
    block: str | None = None
    dimensions_mm: tuple[int, int, int] | None = None
    references: dict[str, str] = field(default_factory=dict)
    raw_segments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedEDIMessage:
    message_reference: str | None
    document_number: str | None
    prepared_at: datetime | None
    containers: list[ParsedContainer]


class EdiCoedorParser:
    """Parser for EDIFACT COEDOR-style messages.

    The parser is intentionally tolerant to minor partner-specific variations in
    qualifiers while still validating mandatory structural requirements.
    """

    _container_pattern = re.compile(r"[A-Z]{4}\d{7}")

    def parse(self, payload: str) -> ParsedEDIMessage:
        try:
            segments = self._split_segments(payload)
            if not segments:
                raise EDIParseError("EDI payload is empty.")

            message_reference: str | None = None
            document_number: str | None = None
            prepared_at: datetime | None = None
            containers: list[ParsedContainer] = []
            current: ParsedContainer | None = None

            for raw_segment in segments:
                tag, elements = self._parse_segment(raw_segment)

                if tag == "UNH":
                    message_reference = self._safe_get(elements, 0)
                elif tag == "BGM":
                    document_number = self._extract_composite_value(self._safe_get(elements, 1))
                elif tag == "DTM":
                    prepared_at = prepared_at or self._parse_dtm(elements)
                elif tag == "EQD":
                    if current is not None:
                        self._finalize_container(current)
                        containers.append(current)
                    current = self._parse_eqd(elements)
                    current.raw_segments.append(raw_segment)
                elif current is not None:
                    current.raw_segments.append(raw_segment)
                    self._apply_container_segment(current, tag, elements)

            if current is not None:
                self._finalize_container(current)
                containers.append(current)

            if not containers:
                raise EDIParseError("No container equipment segments (EQD) found.")

            return ParsedEDIMessage(
                message_reference=message_reference,
                document_number=document_number,
                prepared_at=prepared_at,
                containers=containers,
            )
        except EDIParseError:
            raise
        except Exception as exc:
            raise EDIParseError(f"Failed to parse EDI payload: {exc}") from exc

    def _split_segments(self, payload: str) -> list[str]:
        cleaned = payload.replace("\r", "").replace("\n", "")
        return [segment.strip() for segment in cleaned.split("'") if segment.strip()]

    def _parse_segment(self, segment: str) -> tuple[str, list[str]]:
        parts = [part.strip() for part in segment.split("+")]
        if not parts or not parts[0]:
            raise EDIParseError(f"Invalid segment: {segment}")
        return parts[0], parts[1:]

    def _parse_eqd(self, elements: list[str]) -> ParsedContainer:
        raw_container = self._safe_get(elements, 1) or self._safe_get(elements, 0)
        container_number = self._extract_container_number(raw_container)
        if not container_number:
            raise EDIParseError("EQD segment does not include a valid container number.")

        iso_type_code = self._extract_composite_value(self._safe_get(elements, 2))
        return ParsedContainer(
            container_number=container_number,
            iso_type_code=iso_type_code,
        )

    def _apply_container_segment(self, container: ParsedContainer, tag: str, elements: list[str]) -> None:
        if tag == "MEA":
            self._parse_mea(container, elements)
            return

        if tag == "LOC":
            self._parse_loc(container, elements)
            return

        if tag == "DIM":
            self._parse_dim(container, elements)
            return

        if tag == "RFF":
            self._parse_rff(container, elements)

    def _parse_mea(self, container: ParsedContainer, elements: list[str]) -> None:
        qualifier = self._safe_get(elements, 0) or ""
        measurement = ":".join(elements)
        value = self._extract_last_float(measurement)
        if value is None:
            return

        normalized = qualifier.upper()
        if "AAW" in normalized or "GROSS" in measurement.upper() or "VGM" in measurement.upper():
            container.gross_weight_kg = value
            return
        if normalized in {"T", "TAR", "TARE"} or "TARE" in measurement.upper():
            container.tare_weight_kg = value
            return

        # Fallback: map first MEA with KGM to gross if not set yet.
        if container.gross_weight_kg is None and "KGM" in measurement.upper():
            container.gross_weight_kg = value

    def _parse_loc(self, container: ParsedContainer, elements: list[str]) -> None:
        qualifier = (self._safe_get(elements, 0) or "").upper()
        raw_location = self._safe_get(elements, 1)
        if not raw_location:
            return

        location = self._extract_location_label(raw_location) or ""
        normalized = location.upper()

        block_match = re.search(r"BLOCK[-\s]?([A-Z0-9]+)", normalized)
        bay_match = re.search(r"BAY[-\s]?(\d+)", normalized)
        row_match = re.search(r"ROW[-\s]?(\d+)", normalized)
        tier_match = re.search(r"TIER[-\s]?(\d+)", normalized)

        if block_match:
            container.block = f"BLOCK-{block_match.group(1)}"

        if bay_match:
            container.bay = int(bay_match.group(1))

        if row_match:
            container.row = int(row_match.group(1))

        if tier_match:
            container.tier = int(tier_match.group(1))

        # Common yard slot patterns: BAY/ROW/TIER encoded as 3-2-2 digits.
        digits = "".join(ch for ch in location if ch.isdigit())
        if len(digits) >= 7 and (container.bay is None or container.row is None or container.tier is None):
            container.bay = container.bay if container.bay is not None else int(digits[0:3])
            container.row = container.row if container.row is not None else int(digits[3:5])
            container.tier = container.tier if container.tier is not None else int(digits[5:7])

        if qualifier in {"147", "11", "9", "7"} and container.block is None:
            container.block = location or None

    def _parse_dim(self, container: ParsedContainer, elements: list[str]) -> None:
        joined = ":".join(elements)
        values = [int(float(val)) for val in re.findall(r"\d+(?:\.\d+)?", joined)]
        if len(values) >= 3:
            container.dimensions_mm = (values[0], values[1], values[2])

    def _parse_rff(self, container: ParsedContainer, elements: list[str]) -> None:
        reference = self._safe_get(elements, 0)
        if not reference:
            return
        parts = reference.split(":", 1)
        if len(parts) == 2:
            container.references[parts[0]] = parts[1]

    def _parse_dtm(self, elements: list[str]) -> datetime | None:
        value = self._safe_get(elements, 0)
        if not value:
            return None

        parts = value.split(":")
        if len(parts) < 2:
            return None

        dtm_value = parts[1]
        fmt_code = parts[2] if len(parts) >= 3 else ""

        if fmt_code == "203" and len(dtm_value) == 12:
            return datetime.strptime(dtm_value, "%Y%m%d%H%M")
        if fmt_code == "102" and len(dtm_value) == 8:
            return datetime.strptime(dtm_value, "%Y%m%d")
        return None

    def _finalize_container(self, container: ParsedContainer) -> None:
        if container.gross_weight_kg is not None and container.tare_weight_kg is not None:
            container.payload_weight_kg = max(container.gross_weight_kg - container.tare_weight_kg, 0.0)

    def _extract_container_number(self, value: str | None) -> str | None:
        if not value:
            return None
        match = self._container_pattern.search(value.replace(":", "").upper())
        return match.group(0) if match else None

    def _extract_composite_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        head = value.split(":", 1)[0].strip()
        return head or None

    def _extract_location_label(self, value: str | None) -> str | None:
        if value is None:
            return None

        if "::" in value:
            tail = value.split("::", 1)[1]
            label = tail.split(":", 1)[0].strip()
            if label:
                return label

        return self._extract_composite_value(value)

    def _extract_last_float(self, value: str) -> float | None:
        matches = re.findall(r"-?\d+(?:\.\d+)?", value)
        if not matches:
            return None
        return float(matches[-1])

    def _safe_get(self, values: Iterable[str], index: int) -> str | None:
        values_list = list(values)
        if index < 0 or index >= len(values_list):
            return None
        candidate = values_list[index]
        return candidate if candidate != "" else None


def parse_edifact_coedor(payload: str) -> ParsedEDIMessage:
    parser = EdiCoedorParser()
    return parser.parse(payload)
