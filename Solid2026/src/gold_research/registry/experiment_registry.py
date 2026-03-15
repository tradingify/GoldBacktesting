"""
Experiment Registry.

Maintains a catalog of all historically executed backtests and their metadata.
"""
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, UTC
from pydantic import BaseModel, Field

from src.gold_research.core.paths import ProjectPaths

class ExperimentRecord(BaseModel):
    """Metadata for a successfully executed experiment run."""
    experiment_id: str
    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    strategy_name: str
    dataset_manifest_id: str
    sharpe: Optional[float] = None
    net_profit: Optional[float] = None

class ExperimentRegistry:
    """Manages appending and querying the global experiment log."""
    
    def __init__(self):
        self.registry_file = ProjectPaths.DATA / "manifests" / "experiment_log.json"
        
    def _load(self) -> List[Dict[str, Any]]:
        if not self.registry_file.exists():
            return []
        with open(self.registry_file, 'r') as f:
            return json.load(f)
            
    def _save(self, data: List[Dict[str, Any]]):
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, 'w') as f:
            json.dump(data, f, indent=4)
            
    def register(self, record: ExperimentRecord):
        """Appends a new run to the timeline."""
        data = self._load()
        data.append(record.model_dump())
        self._save(data)
        
    def find_best_by_metric(self, metric: str = "sharpe") -> Optional[ExperimentRecord]:
        """Scans history for the top performer in a category."""
        data = self._load()
        if not data:
            return None
            
        valid = [r for r in data if r.get(metric) is not None]
        if not valid:
            return None
            
        best = max(valid, key=lambda x: x[metric])
        return ExperimentRecord(**best)
