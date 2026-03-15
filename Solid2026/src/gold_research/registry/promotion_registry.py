"""
Promotion Registry.

Tracks the lifecycle state of a specific parameterized run.
States: 'rejected', 'hold_for_review', 'candidate_for_robustness',
'candidate_for_portfolio', 'archived', 'live'.
"""
from typing import Dict, Any, List, Optional
import json
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from src.gold_research.core.paths import ProjectPaths

class PromotionState(str, Enum):
    REJECTED = "rejected"
    HOLD_FOR_REVIEW = "hold_for_review"
    CANDIDATE_FOR_ROBUSTNESS = "candidate_for_robustness"
    CANDIDATE_FOR_PORTFOLIO = "candidate_for_portfolio"
    ARCHIVED = "archived"
    LIVE = "live"

class PromotionRecord(BaseModel):
    run_id: str
    state: PromotionState
    promoted_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    reason: str = ""
    author: str = "System"

class PromotionRegistry:
    """Tracks which hyperparameters 'graduated' the pipeline."""
    
    def __init__(self):
        self.registry_file = ProjectPaths.DATA / "manifests" / "promotion_log.json"
        
    def _load(self) -> List[Dict[str, Any]]:
        if not self.registry_file.exists():
            return []
        with open(self.registry_file, 'r') as f:
            return json.load(f)
            
    def _save(self, data: List[Dict[str, Any]]):
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, 'w') as f:
            json.dump(data, f, indent=4)
            
    def update_state(self, run_id: str, state: PromotionState, reason: str = ""):
        data = self._load()
        # Remove old mapping for this run
        data = [d for d in data if d["run_id"] != run_id]
        
        record = PromotionRecord(run_id=run_id, state=state, reason=reason)
        data.append(record.model_dump())
        self._save(data)
        
    def get_runs_by_state(self, state: PromotionState) -> List[str]:
        data = self._load()
        return [d["run_id"] for d in data if d["state"] == state.value]