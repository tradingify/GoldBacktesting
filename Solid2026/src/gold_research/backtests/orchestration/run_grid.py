"""Exhaustive Grid Search Orchestrator."""
from typing import Dict, Any, List
import logging

from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.backtests.specifications.parameter_grid import ParameterGrid
from src.gold_research.orchestration.batch_runner import enqueue_specs, execute_queued_runs

logger = logging.getLogger("gold_research.orchestration.grid")

def run_grid(base_spec: ExperimentSpec, grid: ParameterGrid, parallel: bool = False) -> List[Dict[str, Any]]:
    """
    Spawns multiple Backtest instances.
    
    Args:
         base_spec: The common parameters (Dates, Instrument, Logic Core)
         grid: The iterable combinations space.
         parallel: If True, uses multiprocessing pool.
         
    Returns:
         List of results.
    """
    logger.info(f"Generating Grid Search space for Experiment: {base_spec.experiment_id}")
    
    combos = list(grid.generate_grid())
    logger.info(f"Grid Space Expanded: {len(combos)} total permutations to queue.")
    queue_summary = enqueue_specs(base_spec, combos, run_type="grid")
    logger.info(
        "Queued %s new grid runs and skipped %s duplicates.",
        queue_summary["submitted"],
        queue_summary["skipped"],
    )

    # Phase 1 batch execution remains sequential even when the legacy flag is set.
    results = execute_queued_runs(experiment_id=base_spec.experiment_id)
    return results
