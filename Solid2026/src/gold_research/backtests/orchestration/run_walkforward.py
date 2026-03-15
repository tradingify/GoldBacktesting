"""Walk-Forward Optimization Orchestrator."""
from typing import Dict, Any, List, Tuple
import logging
import copy
from datetime import datetime, timedelta

from src.gold_research.analytics.robustness import RobustnessAnalyzer
from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.backtests.specifications.parameter_grid import ParameterGrid
from src.gold_research.core.ids import generate_run_fingerprint, generate_run_id
from src.gold_research.pipeline.run_pipeline import run_single_pipeline_with_context

logger = logging.getLogger("gold_research.orchestration.walkforward")

def generate_wfo_windows(start_date: datetime, end_date: datetime, is_days: int, oos_days: int) -> List[Tuple[datetime, datetime, datetime, datetime]]:
    """
    Generates rolling train/test time boundaries.
    
    Returns:
        List of tuples: (IS_Start, IS_End, OOS_Start, OOS_End)
    """
    windows = []
    current_start = start_date
    
    while True:
        is_end = current_start + timedelta(days=is_days)
        oos_start = is_end
        oos_end = oos_start + timedelta(days=oos_days)
        
        if oos_end > end_date:
            break
            
        windows.append((current_start, is_end, oos_start, oos_end))
        current_start = current_start + timedelta(days=oos_days) # Anchored rolling
        
    return windows

def run_walkforward(
    base_spec: ExperimentSpec, 
    grid: ParameterGrid, 
    is_days: int = 365, 
    oos_days: int = 90
) -> Dict[str, Any]:
    """
    Orchestrates the massive rolling WFO pipeline.
    
    Algorithm:
    1. Define rolling time windows (e.g. 1 year train, 3 month test)
    2. For each window:
        a. Run complete Grid Search over `grid` on IS data.
        b. Select "Best" parameter set externally.
        c. Run "Best" parameter set on OOS data.
    3. Aggregate all sequential OOS runs into a single equity curve proxy.
    
    Args:
        base_spec: Foundation blueprint containing absolute start/end boundaries.
        grid: The parameter combinations to explore inside IS windows.
        is_days: In-Sample training length.
        oos_days: Out-Of-Sample forward testing length.
    """
    logger.info(f"Starting Walk-Forward Pipeline for {base_spec.experiment_id}")
    
    if not base_spec.dataset.start_time or not base_spec.dataset.end_time:
         raise ValueError("WFO requires absolute start/end times in DatasetSpec.")
         
    start_dt = datetime.fromisoformat(base_spec.dataset.start_time.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(base_spec.dataset.end_time.replace("Z", "+00:00"))
    
    windows = generate_wfo_windows(start_dt, end_dt, is_days, oos_days)
    logger.info(f"Generated {len(windows)} rolling WFO windows.")
    
    pipeline_results = {
        "is_grid_results": [],
        "oos_live_track": [],
    }
    
    for w_idx, (is_s, is_e, oos_s, oos_e) in enumerate(windows):
        logger.info(f"--- WFO Fold {w_idx+1}/{len(windows)} ---")
        logger.info(f"IS Window: {is_s.date()} -> {is_e.date()}")
        logger.info(f"OOS Window: {oos_s.date()} -> {oos_e.date()}")
        
        # 1. Execute all candidate specs on the IS period.
        is_spec = copy.deepcopy(base_spec)
        is_spec.dataset.start_time = is_s.isoformat()
        is_spec.dataset.end_time = is_e.isoformat()

        is_results = []
        best_result = None
        best_combo = None

        for combo in grid.generate_grid():
            child_spec = copy.deepcopy(is_spec)
            child_spec.strategy_params.update(combo)
            strategy_name = child_spec.strategy_class_path.rsplit(".", 1)[-1]
            child_spec.run_id = generate_run_id(
                child_spec.experiment_id,
                f"{strategy_name}_is_fold_{w_idx}",
                child_spec.strategy_params,
            )
            fingerprint = generate_run_fingerprint(
                experiment_id=child_spec.experiment_id,
                strategy_class_path=child_spec.strategy_class_path,
                strategy_params=child_spec.strategy_params,
                dataset_manifest_id=child_spec.dataset.manifest_id,
                instrument_id=child_spec.dataset.instrument_id,
                start_time=child_spec.dataset.start_time,
                end_time=child_spec.dataset.end_time,
                cost_profile=child_spec.costs.profile_name,
                risk_profile=child_spec.risk.profile_name,
            )
            result = run_single_pipeline_with_context(
                child_spec,
                parent_run_id=base_spec.run_id,
                run_type="walkforward_is",
                fingerprint=fingerprint,
            )
            result_payload = {
                "fold": w_idx,
                "phase": "is",
                "params": combo,
                "run_id": result.run_id,
                "status": result.status,
                "scorecard": result.scorecard.model_dump(),
            }
            is_results.append(result_payload)
            if best_result is None or result.scorecard.sharpe > best_result.scorecard.sharpe:
                best_result = result
                best_combo = combo

        pipeline_results["is_grid_results"].extend(is_results)

        if best_result is None or best_combo is None:
            continue

        oos_spec = copy.deepcopy(base_spec)
        oos_spec.strategy_params.update(best_combo)
        oos_spec.dataset.start_time = oos_s.isoformat()
        oos_spec.dataset.end_time = oos_e.isoformat()
        strategy_name = oos_spec.strategy_class_path.rsplit(".", 1)[-1]
        oos_spec.run_id = generate_run_id(
            oos_spec.experiment_id,
            f"{strategy_name}_oos_fold_{w_idx}",
            oos_spec.strategy_params,
        )
        oos_fingerprint = generate_run_fingerprint(
            experiment_id=oos_spec.experiment_id,
            strategy_class_path=oos_spec.strategy_class_path,
            strategy_params=oos_spec.strategy_params,
            dataset_manifest_id=oos_spec.dataset.manifest_id,
            instrument_id=oos_spec.dataset.instrument_id,
            start_time=oos_spec.dataset.start_time,
            end_time=oos_spec.dataset.end_time,
            cost_profile=oos_spec.costs.profile_name,
            risk_profile=oos_spec.risk.profile_name,
        )
        oos_result = run_single_pipeline_with_context(
            oos_spec,
            parent_run_id=best_result.run_id,
            run_type="walkforward_oos",
            fingerprint=oos_fingerprint,
        )
        pipeline_results["oos_live_track"].append(
            {
                "fold": w_idx,
                "phase": "oos",
                "selected_params": best_combo,
                "is_run_id": best_result.run_id,
                "run_id": oos_result.run_id,
                "status": oos_result.status,
                "scorecard": oos_result.scorecard.model_dump(),
            }
        )

    pipeline_results["summary"] = RobustnessAnalyzer.summarize_walkforward(
        pipeline_results["is_grid_results"],
        pipeline_results["oos_live_track"],
    )
    return pipeline_results
