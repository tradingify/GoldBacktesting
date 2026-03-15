"""Randomized Search Orchestrator."""
import logging
from typing import Dict, Any, List

from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.backtests.specifications.parameter_grid import ParameterGrid
from src.gold_research.orchestration.batch_runner import enqueue_specs, execute_queued_runs

logger = logging.getLogger("gold_research.orchestration.random")

def run_random_search(base_spec: ExperimentSpec, grid: ParameterGrid, n_samples: int, parallel: bool = False) -> List[Dict[str, Any]]:
    """
    Spawns N randomly sampled Backtest instances.
    """
    logger.info(f"Generating Random {n_samples}-sample space for: {base_spec.experiment_id}")
    
    combos = list(grid.generate_random(n_samples))
    queue_summary = enqueue_specs(base_spec, combos, run_type="random")
    logger.info(
        "Queued %s new random-search runs and skipped %s duplicates.",
        queue_summary["submitted"],
        queue_summary["skipped"],
    )

    # Phase 1 batch execution remains sequential even when the legacy flag is set.
    results = execute_queued_runs(experiment_id=base_spec.experiment_id)
    return results
