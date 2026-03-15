"""Queue-aware batch orchestration for grid and random search runs."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable
import json

from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.core.ids import generate_run_fingerprint, generate_run_id
from src.gold_research.pipeline.run_pipeline import run_single_pipeline_with_context
from src.gold_research.store.queue_repo import QueueRepository


def _spec_fingerprint(spec: ExperimentSpec) -> str:
    """Compute the dedupe fingerprint for a spec."""
    return generate_run_fingerprint(
        experiment_id=spec.experiment_id,
        strategy_class_path=spec.strategy_class_path,
        strategy_params=spec.strategy_params,
        dataset_manifest_id=spec.dataset.manifest_id,
        instrument_id=spec.dataset.instrument_id,
        start_time=spec.dataset.start_time,
        end_time=spec.dataset.end_time,
        cost_profile=spec.costs.profile_name,
        risk_profile=spec.risk.profile_name,
    )


def _strategy_name(strategy_class_path: str) -> str:
    """Get the leaf class name from the dotted class path."""
    return strategy_class_path.rsplit(".", 1)[-1]


def prepare_child_spec(
    base_spec: ExperimentSpec,
    combo: dict,
    run_type: str,
) -> tuple[ExperimentSpec, str]:
    """Create a child spec and its stable dedupe fingerprint."""
    spec_variant = deepcopy(base_spec)
    spec_variant.strategy_params.update(combo)
    strategy_name = _strategy_name(spec_variant.strategy_class_path)
    spec_variant.run_id = generate_run_id(spec_variant.experiment_id, strategy_name, spec_variant.strategy_params)
    fingerprint = _spec_fingerprint(spec_variant)
    return spec_variant, fingerprint


def enqueue_specs(
    base_spec: ExperimentSpec,
    combos: Iterable[dict],
    *,
    run_type: str,
) -> dict:
    """Queue child run specs for later execution, skipping duplicates."""
    queue_repo = QueueRepository()
    submitted = 0
    skipped = 0
    child_run_ids: list[str] = []

    for combo in combos:
        child_spec, fingerprint = prepare_child_spec(base_spec, combo, run_type)
        inserted = queue_repo.enqueue(
            run_id=child_spec.run_id,
            experiment_id=child_spec.experiment_id,
            parent_run_id=base_spec.run_id,
            run_type=run_type,
            fingerprint=fingerprint,
            spec_json=child_spec.model_dump(),
        )
        if inserted:
            submitted += 1
            child_run_ids.append(child_spec.run_id)
        else:
            skipped += 1

    return {
        "submitted": submitted,
        "skipped": skipped,
        "child_run_ids": child_run_ids,
    }


def execute_queued_runs(experiment_id: str | None = None) -> list[dict]:
    """Execute queued runs sequentially through the canonical pipeline."""
    queue_repo = QueueRepository()
    queued_rows = queue_repo.list_by_status("queued", experiment_id=experiment_id)
    results: list[dict] = []

    for row in queued_rows:
        spec = ExperimentSpec(**json.loads(row["spec_json"]))
        queue_repo.update_status(spec.run_id, "running")
        try:
            result = run_single_pipeline_with_context(
                spec,
                parent_run_id=row.get("parent_run_id"),
                run_type=row.get("run_type"),
                fingerprint=row.get("fingerprint"),
            )
            queue_repo.update_status(spec.run_id, "completed")
            results.append(
                {
                    "run_id": result.run_id,
                    "status": result.status,
                    "run_dir": str(result.run_dir),
                }
            )
        except Exception:
            queue_repo.update_status(spec.run_id, "failed")
            raise

    return results
