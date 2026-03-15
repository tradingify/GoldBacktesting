"""Single Backtest Orchestrator."""
from typing import Dict, Any
import logging

from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.pipeline.run_pipeline import run_single_pipeline_with_context

logger = logging.getLogger("gold_research.orchestration.single")

def run_single(spec: ExperimentSpec) -> Dict[str, Any]:
    """
    Synchronously runs a single Nautilus Engine.
    
    Args:
        spec: The fully qualified declarative experiment blueprint.
        
    Returns:
        Structured results map.
    """
    logger.info(f"Starting single run: {spec.run_id}")
    result = run_single_pipeline_with_context(spec)
    logger.info(f"Run {spec.run_id} complete with status {result.status}. Outputs at {result.run_dir}")
    return {
        "run_id": result.run_id,
        "experiment_id": result.experiment_id,
        "status": result.status,
        "run_dir": str(result.run_dir),
        "artifacts": result.artifacts,
        "scorecard": result.scorecard.model_dump(),
        "error_text": result.error_text,
    }

if __name__ == "__main__":
    from src.gold_research.backtests.specifications.experiment_spec import DatasetSpec
    import uuid
    # Scaffold example usage
    stub_spec = ExperimentSpec(
         experiment_id="TEST_MACROSS_01",
         run_id=f"run_{uuid.uuid4().hex[:8]}",
         strategy_class_path="src.gold_research.strategies.trend.moving_average_cross.MovingAverageCross",
         strategy_params={"fast_period": 10, "slow_period": 30},
         dataset=DatasetSpec(manifest_id="gold_m5_2023", instrument_id="XAUUSD-IDEALPRO-USD")
    )
    
    # Uncomment to actually invoke
    # run_single(stub_spec)
