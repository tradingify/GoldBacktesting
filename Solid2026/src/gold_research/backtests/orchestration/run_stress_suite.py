"""Stress Suite Orchestrator."""
from typing import Dict, Any, List
import logging
import copy

from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.analytics.robustness import RobustnessAnalyzer
from src.gold_research.core.ids import generate_run_fingerprint, generate_run_id
from src.gold_research.pipeline.run_pipeline import run_single_pipeline_with_context

logger = logging.getLogger("gold_research.orchestration.stress")

def run_stress_suite(winner_spec: ExperimentSpec) -> List[Dict[str, Any]]:
    """
    Identifies fragility in a backtested strategy.
    
    Mechanics:
    Forces the strategy to trade in 'optimistic', 'base', and 'harsh'
    friction profiles defined in `costs.yaml` sequentially.
    """
    logger.info(f"Commencing Friction Stress Test for Winner: {winner_spec.run_id}")
    
    stress_profiles = ["optimistic", "base", "harsh"]
    suite_results = []
    
    for profile in stress_profiles:
        logger.info(f"Executing under '{profile}' regime...")
        stress_spec = copy.deepcopy(winner_spec)
        stress_spec.costs.profile_name = profile
        strategy_name = stress_spec.strategy_class_path.rsplit(".", 1)[-1]
        stress_spec.run_id = generate_run_id(
            stress_spec.experiment_id,
            f"{strategy_name}_{profile}",
            {
                **stress_spec.strategy_params,
                "cost_profile": profile,
                "run_type": "stress",
            },
        )
        fingerprint = generate_run_fingerprint(
            experiment_id=stress_spec.experiment_id,
            strategy_class_path=stress_spec.strategy_class_path,
            strategy_params=stress_spec.strategy_params,
            dataset_manifest_id=stress_spec.dataset.manifest_id,
            instrument_id=stress_spec.dataset.instrument_id,
            start_time=stress_spec.dataset.start_time,
            end_time=stress_spec.dataset.end_time,
            cost_profile=stress_spec.costs.profile_name,
            risk_profile=stress_spec.risk.profile_name,
        )
        result = run_single_pipeline_with_context(
            stress_spec,
            parent_run_id=winner_spec.run_id,
            run_type="stress",
            fingerprint=fingerprint,
        )
        suite_results.append({
            "stress_profile": profile,
            "run_id": result.run_id,
            "status": result.status,
            "scorecard": result.scorecard.model_dump(),
            "run_dir": str(result.run_dir),
        })

    return {
        "parent_run_id": winner_spec.run_id,
        "suite_results": suite_results,
        "summary": RobustnessAnalyzer.summarize_stress_suite(suite_results),
    }
