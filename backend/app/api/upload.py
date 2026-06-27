from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.edi_parser import EDIParseError, ParsedContainer, parse_edifact_coedor
from app.core.safety_engine import ContainerSafetyInput, SafetyEngine
from app.models.database import (
    Container,
    ContainerPlacement,
    ProcessingStatus,
    SafetyEvaluation,
    SafetyStatus as DbSafetyStatus,
    UploadBatch,
    YardBlock,
    YardSlot,
    get_db_session,
)


router = APIRouter(prefix="/upload", tags=["upload"])


class UploadSummaryResponse(BaseModel):
    batch_id: uuid.UUID
    source_filename: str
    processing_status: str
    total_containers: int
    created_containers: int
    created_evaluations: int
    warnings: list[str] = Field(default_factory=list)


def _coerce_number(value: float | None, default: float = 0.0) -> float:
    return value if value is not None else default


async def _get_or_create_slot(
    session: AsyncSession,
    parsed: ParsedContainer,
) -> tuple[YardSlot | None, str | None]:
    if parsed.bay is None or parsed.row is None or parsed.tier is None:
        return None, None

    block_code = parsed.block or "UNKNOWN"
    block_stmt = select(YardBlock).where(YardBlock.code == block_code)
    block = (await session.execute(block_stmt)).scalar_one_or_none()
    if block is None:
        block = YardBlock(code=block_code, description="Auto-generated from EDI upload")
        session.add(block)
        await session.flush()

    slot_stmt = select(YardSlot).where(
        YardSlot.block_id == block.id,
        YardSlot.bay == parsed.bay,
        YardSlot.row == parsed.row,
        YardSlot.tier == parsed.tier,
    )
    slot = (await session.execute(slot_stmt)).scalar_one_or_none()
    if slot is None:
        slot = YardSlot(
            block_id=block.id,
            bay=parsed.bay,
            row=parsed.row,
            tier=parsed.tier,
            max_stack_weight_kg=120000.0,
        )
        session.add(slot)
        await session.flush()

    return slot, block_code
def _build_safety_input(
    container: Container,
    parsed: ParsedContainer,
    stack_metrics: dict[str, float],
    high_wind_mode: bool,
    high_racking_mode: bool,
) -> ContainerSafetyInput:
    dimensions = parsed.dimensions_mm or (12192, 2438, 2591)
    length_m = max(dimensions[0] / 1000.0, 0.1)
    height_m = max(dimensions[2] / 1000.0, 0.1)

    bay = parsed.bay or 0
    row = parsed.row or 0
    tier = parsed.tier or 1
    stack_height_tiers = int(stack_metrics.get("stack_height_tiers", max(tier, 1)))
    stacked_above_weight_kg = float(stack_metrics.get("stacked_above_weight_kg", 0.0))
    tier_supported_weight_kg = float(
        stack_metrics.get("tier_supported_weight_kg", container.gross_weight_kg)
    )

    iso = (container.iso_type_code or "").upper()
    lashing_capacity_kn = 120.0 if iso.startswith("22") else 90.0 if iso.startswith("45") else 100.0
    if high_racking_mode and iso.startswith("45"):
        lashing_capacity_kn *= 0.5

    wind_speed_mps = 30.0 if high_wind_mode else 15.0

    return ContainerSafetyInput(
        container_number=container.container_number,
        gross_weight_kg=container.gross_weight_kg,
        tare_weight_kg=container.tare_weight_kg,
        payload_weight_kg=container.payload_weight_kg,
        bay=bay,
        row=row,
        tier=tier,
        stack_height_tiers=stack_height_tiers,
        stacked_above_weight_kg=stacked_above_weight_kg,
        tier_supported_weight_kg=tier_supported_weight_kg,
        corner_post_capacity_kg=86400.0,
        wind_speed_mps=wind_speed_mps,
        projected_side_area_m2=length_m * height_m,
        lashing_capacity_kn=lashing_capacity_kn,
        center_of_gravity_offset_m=0.0,
    )


@router.post(
    "/edi",
    response_model=UploadSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_edi_file(
    file: UploadFile = File(...),
    uploaded_by: str | None = Form(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> UploadSummaryResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")

    payload_bytes = await file.read()
    if not payload_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    batch = UploadBatch(
        source_filename=file.filename,
        file_sha256=payload_hash,
        uploaded_by=uploaded_by,
        processing_status=ProcessingStatus.PENDING,
    )

    session.add(batch)
    await session.flush()

    try:
        payload_text = payload_bytes.decode("utf-8", errors="ignore")
        parsed_message = parse_edifact_coedor(payload_text)
        batch.processing_status = ProcessingStatus.PARSED

        document_number = (parsed_message.document_number or "").upper()
        high_wind_mode = "WIND" in document_number
        high_racking_mode = "RACKING" in document_number

        stack_groups: dict[tuple[str, int, int], list[ParsedContainer]] = {}
        for item in parsed_message.containers:
            key = (item.block or "UNKNOWN", item.bay or 0, item.row or 0)
            stack_groups.setdefault(key, []).append(item)

        stack_metrics_by_container: dict[str, dict[str, float]] = {}
        for stack_items in stack_groups.values():
            ordered = sorted(stack_items, key=lambda value: value.tier or 1)
            stack_weights = [_coerce_number(value.gross_weight_kg) for value in ordered]
            stack_height = len(ordered)

            for idx, parsed_item in enumerate(ordered):
                stacked_above = sum(stack_weights[idx + 1 :])
                supported_weight = stack_weights[idx] + stacked_above
                stack_metrics_by_container[parsed_item.container_number] = {
                    "stack_height_tiers": float(stack_height),
                    "stacked_above_weight_kg": stacked_above,
                    "tier_supported_weight_kg": supported_weight,
                }

        safety_engine = SafetyEngine()
        warning_messages: list[str] = []
        created_containers = 0
        created_evaluations = 0

        for parsed_container in parsed_message.containers:
            gross = _coerce_number(parsed_container.gross_weight_kg)
            tare = _coerce_number(parsed_container.tare_weight_kg)
            payload = _coerce_number(parsed_container.payload_weight_kg, max(gross - tare, 0.0))

            container = Container(
                batch_id=batch.id,
                container_number=parsed_container.container_number,
                iso_type_code=parsed_container.iso_type_code,
                gross_weight_kg=gross,
                tare_weight_kg=tare,
                payload_weight_kg=payload,
                cargo_description=parsed_container.references.get("AAA") if parsed_container.references else None,
                edi_payload={
                    "raw_segments": parsed_container.raw_segments,
                    "references": parsed_container.references,
                    "dimensions_mm": parsed_container.dimensions_mm,
                    "position": {
                        "block": parsed_container.block,
                        "bay": parsed_container.bay,
                        "row": parsed_container.row,
                        "tier": parsed_container.tier,
                    },
                },
            )
            session.add(container)
            await session.flush()
            created_containers += 1

            slot, _ = await _get_or_create_slot(session, parsed_container)
            if slot is not None:
                placement = ContainerPlacement(
                    container_id=container.id,
                    slot_id=slot.id,
                    is_active=True,
                )
                session.add(placement)

            stack_metrics = stack_metrics_by_container.get(parsed_container.container_number, {})
            safety_input = _build_safety_input(
                container,
                parsed_container,
                stack_metrics,
                high_wind_mode,
                high_racking_mode,
            )
            evaluation = safety_engine.evaluate_container(safety_input)

            db_eval = SafetyEvaluation(
                batch_id=batch.id,
                container_id=container.id,
                status=DbSafetyStatus(evaluation.status.value),
                overall_score=evaluation.overall_score,
                racking_ok=evaluation.rules["racking"].ok,
                racking_ratio=evaluation.rules["racking"].ratio,
                wind_ok=evaluation.rules["wind"].ok,
                wind_exposure_ratio=evaluation.rules["wind"].ratio,
                weight_distribution_ok=evaluation.rules["weight_distribution"].ok,
                center_of_gravity_offset_m=safety_input.center_of_gravity_offset_m,
                tier_metrics_ok=evaluation.rules["tier_metrics"].ok,
                tier_load_ratio=evaluation.rules["tier_metrics"].ratio,
                corner_post_stress_ok=evaluation.rules["corner_post_stress"].ok,
                corner_post_stress_ratio=evaluation.rules["corner_post_stress"].ratio,
                rule_details={
                    key: {
                        "ok": result.ok,
                        "ratio": result.ratio,
                        "message": result.message,
                    }
                    for key, result in evaluation.rules.items()
                },
                remediation_actions=evaluation.violations,
                evaluated_at=datetime.now(timezone.utc),
            )
            session.add(db_eval)
            created_evaluations += 1

            if evaluation.violations:
                warning_messages.append(
                    f"{container.container_number}: {', '.join(evaluation.violations)}"
                )

        batch.total_containers = created_containers
        batch.processing_status = ProcessingStatus.EVALUATED
        batch.processed_at = datetime.now(timezone.utc)
        await session.commit()

        return UploadSummaryResponse(
            batch_id=batch.id,
            source_filename=batch.source_filename,
            processing_status=batch.processing_status.value,
            total_containers=batch.total_containers,
            created_containers=created_containers,
            created_evaluations=created_evaluations,
            warnings=warning_messages,
        )
    except EDIParseError as exc:
        batch.processing_status = ProcessingStatus.FAILED
        batch.parse_error = str(exc)
        batch.processed_at = datetime.now(timezone.utc)
        await session.commit()
        raise HTTPException(status_code=400, detail=f"EDI parsing failed: {exc}") from exc
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {exc}") from exc
