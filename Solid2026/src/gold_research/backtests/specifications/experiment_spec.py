"""
Experiment Specifications.

Defines the declarative data structures used to define what a backtest 
actually is, separated entirely from how it executes.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class DatasetSpec(BaseModel):
    """Identifies the target data for an experiment."""
    manifest_id: str
    instrument_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class RiskSpec(BaseModel):
    """Declares the risk parameters for the experiment."""
    profile_name: str = "base"
    starting_capital: float = 100000.0
    
class CostSpec(BaseModel):
    """Declares the friction profile for the experiment."""
    profile_name: str = "base"

class ExperimentSpec(BaseModel):
    """
    The master declarative template for a single deterministic Backtest Run.
    No execution logic lives here.
    """
    experiment_id: str
    run_id: str
    strategy_class_path: str
    strategy_params: Dict[str, Any]
    dataset: DatasetSpec
    risk: RiskSpec = Field(default_factory=RiskSpec)
    costs: CostSpec = Field(default_factory=CostSpec)
    
    # Metadata for reporting
    author: str = "GoldResearch"
    tags: List[str] = Field(default_factory=list)
    description: str = ""