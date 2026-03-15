"""Automatic walk-forward and stress validation for successful runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import traceback

from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.backtests.specifications.parameter_grid import ParameterGrid
from src.gold_research.core.artifacts import write_json
from src.gold_research.core.config import load_yaml
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.gates.validation import evaluate_validation
from src.gold_research.store.promotions_repo import PromotionsRepository


@dataclass
class ValidationAutomationConfig:
    """Config knobs for post-screening validation."""

    enabled: bool
    eligible_run_types: set[str]
    eligible_screening_statuses: set[str]
    walkforward_is_days: int
    walkforward_oos_days: int
    numeric_step_pct: float
    min_int_step: int
    min_float_step: float


def load_validation_automation_config() -> ValidationAutomationConfig:
    """Load validation automation settings from global evaluation config."""
    raw = load_yaml(ProjectPaths.CONFIG_GLOBAL / "evaluation.yaml")
    config = raw.get("validation_automation", {})
    return ValidationAutomationConfig(
        enabled=bool(config.get("enabled", True)),
        eligible_run_types=set(config.get("eligible_run_types", ["single"])),
        eligible_screening_statuses=set(config.get("eligible_screening_statuses", ["pass", "soft_fail"])),
        walkforward_is_days=int(config.get("walkforward_is_days", 14)),
        walkforward_oos_days=int(config.get("walkforward_oos_days", 7)),
        numeric_step_pct=float(config.get("numeric_step_pct", 0.20)),
        min_int_step=int(config.get("min_int_step", 1)),
        min_float_step=float(config.get("min_float_step", 0.1)),
    )


def should_auto_validate(run_type: str | None, screening_status: str, completed_status: str) -> bool:
    """Return whether a completed run should receive automatic validation."""
    config = load_validation_automation_config()
    normalized_run_type = run_type or "single"
    return (
        config.enabled
        and completed_status == "COMPLETED"
        and normalized_run_type in config.eligible_run_types
        and screening_status in config.eligible_screening_statuses
    )


def _neighbor_values(value: Any, config: ValidationAutomationConfig) -> list[Any]:
    """Generate a small local neighborhood around a numeric parameter."""
    if isinstance(value, bool):
        return [value]
    if isinstance(value, int):
        step = max(config.min_int_step, int(round(abs(value) * config.numeric_step_pct)))
        values = {max(1, value - step), value, value + step}
        return sorted(values)
    if isinstance(value, float):
        step = max(config.min_float_step, abs(value) * config.numeric_step_pct)
        values = {round(max(0.0001, value - step), 4), round(value, 4), round(value + step, 4)}
        return sorted(values)
    return [value]


def build_validation_grid(strategy_params: dict[str, Any]) -> ParameterGrid:
    """Create a local parameter neighborhood for walk-forward validation."""
    config = load_validation_automation_config()
    param_space: dict[str, list[Any]] = {}
    for key, value in strategy_params.items():
        if key == "timeframe":
            param_space[key] = [value]
            continue
        param_space[key] = _neighbor_values(value, config)
    return ParameterGrid(param_space)


def run_automatic_validation(
    spec: ExperimentSpec,
    *,
    run_dir: Path,
    screening_status: str,
    run_type: str | None,
) -> dict[str, Any]:
    """Run walk-forward and stress validation and persist the combined decision."""
    summary_path = run_dir / "validation_summary.json"
    if not should_auto_validate(run_type, screening_status, "COMPLETED"):
        payload = {
            "run_id": spec.run_id,
            "automation_status": "skipped",
            "reason": "Run is not eligible for automatic validation.",
            "screening_status": screening_status,
            "run_type": run_type or "single",
        }
        write_json(summary_path, payload)
        return payload

    try:
        walkforward_runner = globals().get("run_walkforward")
        stress_runner = globals().get("run_stress_suite")
        if walkforward_runner is None:
            from src.gold_research.backtests.orchestration.run_walkforward import run_walkforward as walkforward_runner
        if stress_runner is None:
            from src.gold_research.backtests.orchestration.run_stress_suite import run_stress_suite as stress_runner

        config = load_validation_automation_config()
        validation_grid = build_validation_grid(spec.strategy_params)
        walkforward = walkforward_runner(
            spec,
            validation_grid,
            is_days=config.walkforward_is_days,
            oos_days=config.walkforward_oos_days,
        )
        stress = stress_runner(spec)
        combined_summary = {
            "wfo_efficiency": walkforward.get("summary", {}).get("wfo_efficiency", 0.0),
            "stress_decay": stress.get("summary", {}).get("stress_decay", 0.0),
            "walkforward_folds": walkforward.get("summary", {}).get("folds", 0),
        }
        decision = evaluate_validation(combined_summary)
        payload = {
            "run_id": spec.run_id,
            "automation_status": "completed",
            "walkforward": walkforward,
            "stress": stress,
            "decision": {
                "gate_name": decision.gate_name,
                "status": decision.status,
                "promotion_state": decision.promotion_state,
                "reason": decision.reason,
                "details": decision.details,
            },
        }
        write_json(summary_path, payload)
        promotions_repo = PromotionsRepository()
        promotions_repo.upsert_gate_result(
            run_id=spec.run_id,
            gate_name=decision.gate_name,
            status=decision.status,
            score=combined_summary["wfo_efficiency"],
            details=payload,
        )
        promotions_repo.upsert_promotion(
            run_id=spec.run_id,
            promotion_state=decision.promotion_state,
            reason=decision.reason,
        )
        return payload
    except Exception as exc:
        payload = {
            "run_id": spec.run_id,
            "automation_status": "failed",
            "screening_status": screening_status,
            "run_type": run_type or "single",
            "error_text": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        }
        write_json(summary_path, payload)
        return payload
