"""Validation-stage gates based on walk-forward and stress outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from src.gold_research.core.config import load_yaml
from src.gold_research.core.paths import ProjectPaths


@dataclass
class ValidationDecision:
    """Structured decision for a validation/falsification checkpoint."""

    gate_name: str
    status: str
    promotion_state: str
    reason: str
    details: dict


def _validation_thresholds() -> dict:
    """Load thresholds for candidate_for_portfolio promotion."""
    config = load_yaml(ProjectPaths.CONFIG_GLOBAL / "evaluation.yaml")
    thresholds = config.get("promotion_thresholds", {}).get("candidate_for_portfolio", {})
    return {
        "min_wfo_efficiency": float(thresholds.get("min_wfo_efficiency", 0.50)),
        "max_harsh_stress_decay": float(thresholds.get("max_harsh_stress_decay", 0.50)),
    }


def evaluate_validation(summary: dict) -> ValidationDecision:
    """Evaluate combined walk-forward and stress summaries."""
    thresholds = _validation_thresholds()
    wfo_efficiency = float(summary.get("wfo_efficiency", 0.0))
    stress_decay = float(summary.get("stress_decay", 0.0))

    checks = {
        "wfo_efficiency": wfo_efficiency >= thresholds["min_wfo_efficiency"],
        "stress_decay": stress_decay >= thresholds["max_harsh_stress_decay"],
    }

    if all(checks.values()):
        return ValidationDecision(
            gate_name="validation",
            status="pass",
            promotion_state="candidate_for_portfolio",
            reason="Run family passed walk-forward and harsh-friction validation.",
            details={"thresholds": thresholds, "checks": checks, "summary": summary},
        )

    if any(checks.values()):
        return ValidationDecision(
            gate_name="validation",
            status="soft_fail",
            promotion_state="hold_for_review",
            reason="Run family passed some but not all validation thresholds.",
            details={"thresholds": thresholds, "checks": checks, "summary": summary},
        )

    return ValidationDecision(
        gate_name="validation",
        status="hard_fail",
        promotion_state="rejected",
        reason="Run family failed walk-forward and harsh-friction validation.",
        details={"thresholds": thresholds, "checks": checks, "summary": summary},
    )
