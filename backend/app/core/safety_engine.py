from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class SafetyStatus(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class ISO1496Config:
    max_gross_weight_kg: float = 30480.0
    max_payload_weight_kg: float = 28200.0
    max_stack_height_tiers: int = 6
    max_corner_post_load_kg: float = 86400.0
    max_tier_load_ratio: float = 1.0
    max_cog_offset_m: float = 0.60
    max_wind_exposure_ratio: float = 1.0
    max_racking_ratio: float = 1.0


@dataclass(slots=True)
class ContainerSafetyInput:
    container_number: str
    gross_weight_kg: float
    tare_weight_kg: float
    payload_weight_kg: float
    bay: int
    row: int
    tier: int
    stack_height_tiers: int
    stacked_above_weight_kg: float
    tier_supported_weight_kg: float
    corner_post_capacity_kg: float
    wind_speed_mps: float
    projected_side_area_m2: float
    lashing_capacity_kn: float
    center_of_gravity_offset_m: float


@dataclass(slots=True)
class RuleResult:
    name: str
    ok: bool
    ratio: float
    message: str


@dataclass(slots=True)
class SafetyEvaluation:
    container_number: str
    status: SafetyStatus
    overall_score: float
    rules: dict[str, RuleResult] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)


class SafetyEngine:
    """Evaluates five safety rules plus explicit ISO 1496-1 limits."""

    def __init__(self, config: ISO1496Config | None = None) -> None:
        self.config = config or ISO1496Config()

    def evaluate_container(self, item: ContainerSafetyInput) -> SafetyEvaluation:
        violations = self.validate_iso_1496_weights_and_stack_heights(item)

        rule_results = {
            "racking": self._rule_racking(item),
            "wind": self._rule_wind(item),
            "weight_distribution": self._rule_weight_distribution(item),
            "tier_metrics": self._rule_tier_metrics(item),
            "corner_post_stress": self._rule_corner_post_stress(item),
        }

        failed_rules = [rule.name for rule in rule_results.values() if not rule.ok]
        violations.extend(failed_rules)

        overall_score = self._score(rule_results)
        status = self._status(violations, overall_score)

        return SafetyEvaluation(
            container_number=item.container_number,
            status=status,
            overall_score=overall_score,
            rules=rule_results,
            violations=violations,
        )

    def evaluate_batch(self, items: list[ContainerSafetyInput]) -> list[SafetyEvaluation]:
        return [self.evaluate_container(item) for item in items]

    def validate_iso_1496_weights_and_stack_heights(self, item: ContainerSafetyInput) -> list[str]:
        violations: list[str] = []

        if item.gross_weight_kg > self.config.max_gross_weight_kg:
            violations.append(
                f"gross_weight_exceeds_iso1496 ({item.gross_weight_kg:.1f}kg > {self.config.max_gross_weight_kg:.1f}kg)"
            )

        if item.payload_weight_kg > self.config.max_payload_weight_kg:
            violations.append(
                f"payload_weight_exceeds_iso1496 ({item.payload_weight_kg:.1f}kg > {self.config.max_payload_weight_kg:.1f}kg)"
            )

        if item.stack_height_tiers > self.config.max_stack_height_tiers:
            violations.append(
                "stack_height_exceeds_iso1496 "
                f"({item.stack_height_tiers} > {self.config.max_stack_height_tiers})"
            )

        if item.gross_weight_kg < item.tare_weight_kg:
            violations.append("gross_weight_below_tare_weight")

        return violations

    def _rule_racking(self, item: ContainerSafetyInput) -> RuleResult:
        # Simplified racking ratio proxy: transverse inertia against lashing capacity.
        dynamic_force_kn = (item.gross_weight_kg * 9.81 * 0.25) / 1000.0
        racking_ratio = self._safe_div(dynamic_force_kn, item.lashing_capacity_kn)
        ok = racking_ratio <= self.config.max_racking_ratio
        return RuleResult(
            name="racking",
            ok=ok,
            ratio=racking_ratio,
            message=(
                "Racking within limit" if ok else "Racking load exceeds lashing design limit"
            ),
        )

    def _rule_wind(self, item: ContainerSafetyInput) -> RuleResult:
        # Wind pressure q = 0.613 * v^2 (N/m^2), force = qA.
        wind_force_kn = (0.613 * (item.wind_speed_mps ** 2) * item.projected_side_area_m2) / 1000.0
        resisting_kn = max(item.lashing_capacity_kn * 0.7, 1e-6)
        exposure_ratio = self._safe_div(wind_force_kn, resisting_kn)
        ok = exposure_ratio <= self.config.max_wind_exposure_ratio
        return RuleResult(
            name="wind",
            ok=ok,
            ratio=exposure_ratio,
            message="Wind load acceptable" if ok else "Wind exposure above safe envelope",
        )

    def _rule_weight_distribution(self, item: ContainerSafetyInput) -> RuleResult:
        offset_ratio = self._safe_div(abs(item.center_of_gravity_offset_m), self.config.max_cog_offset_m)
        ok = offset_ratio <= 1.0
        return RuleResult(
            name="weight_distribution",
            ok=ok,
            ratio=offset_ratio,
            message="Weight distribution balanced" if ok else "Center of gravity offset too high",
        )

    def _rule_tier_metrics(self, item: ContainerSafetyInput) -> RuleResult:
        tier_ratio = self._safe_div(item.tier_supported_weight_kg, max(item.gross_weight_kg, 1e-6))
        height_ratio = self._safe_div(item.stack_height_tiers, self.config.max_stack_height_tiers)
        combined_ratio = max(tier_ratio, height_ratio)
        ok = combined_ratio <= self.config.max_tier_load_ratio
        return RuleResult(
            name="tier_metrics",
            ok=ok,
            ratio=combined_ratio,
            message="Tier load and height are compliant" if ok else "Tier load/height exceed limits",
        )

    def _rule_corner_post_stress(self, item: ContainerSafetyInput) -> RuleResult:
        applied_per_post = self._safe_div(item.stacked_above_weight_kg + item.gross_weight_kg, 4.0)
        capacity_per_post = self._safe_div(item.corner_post_capacity_kg, 4.0)
        stress_ratio = self._safe_div(applied_per_post, max(capacity_per_post, 1e-6))
        ok = stress_ratio <= 1.0
        return RuleResult(
            name="corner_post_stress",
            ok=ok,
            ratio=stress_ratio,
            message="Corner post stress within limits" if ok else "Corner post stress exceeds limits",
        )

    def _score(self, results: dict[str, RuleResult]) -> float:
        if not results:
            return 0.0
        penalties = [min(max(result.ratio - 1.0, 0.0), 1.0) for result in results.values()]
        mean_penalty = sum(penalties) / len(penalties)
        return round(max(0.0, 100.0 * (1.0 - mean_penalty)), 2)

    def _status(self, violations: list[str], score: float) -> SafetyStatus:
        critical_terms = {
            "gross_weight_exceeds_iso1496",
            "payload_weight_exceeds_iso1496",
            "stack_height_exceeds_iso1496",
            "corner_post_stress",
            "tier_metrics",
        }
        if any(any(term in violation for term in critical_terms) for violation in violations):
            return SafetyStatus.CRITICAL
        if score < 85.0 or violations:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE

    def _safe_div(self, numerator: float, denominator: float) -> float:
        if math.isclose(denominator, 0.0):
            return float("inf")
        return numerator / denominator


def evaluate_safety_batch(
    items: list[ContainerSafetyInput],
    config: ISO1496Config | None = None,
) -> list[SafetyEvaluation]:
    engine = SafetyEngine(config=config)
    return engine.evaluate_batch(items)
