"""
Standardized data structures for tracking artifacts and results.

Contains schemas representing Experiment manifests, Run metadata, 
and performance evaluation outputs.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.gold_research.core.enums import StrategyFamily, Timeframe

@dataclass
class ExperimentMetadata:
    """Tracks defining states of a generated experiment."""
    experiment_id: str
    dataset_version: str
    instrument: str
    timeframes: List[str]
    strategy_families: List[str]
    parameters: Dict[str, Any]

@dataclass
class RunSummary:
    """Artifact summarizing a successfully evaluated strategy backtest."""
    run_id: str
    experiment_id: str
    strategy_name: str
    family: StrategyFamily
    timeframe: Timeframe
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "started"
    metrics: Dict[str, float] = field(default_factory=dict)
