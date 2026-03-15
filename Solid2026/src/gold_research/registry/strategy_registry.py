"""
Strategy Registry.

A catalog of available Strategy Templates (logic hypotheses) currently
supported by the engine.
"""
from typing import Dict, Any, List
import json
from pydantic import BaseModel

from src.gold_research.core.paths import ProjectPaths

class StrategyDefinition(BaseModel):
    """Metadata for a strategy logic class."""
    name: str # e.g. "DonchianBreakout"
    family: str # e.g. "trend"
    class_path: str 
    description: str

class StrategyRegistry:
    """Manages available templates."""
    
    def __init__(self):
        self.registry_file = ProjectPaths.DATA / "manifests" / "available_strategies.json"
        
    def _load(self) -> List[Dict[str, Any]]:
        if not self.registry_file.exists():
            return []
        with open(self.registry_file, 'r') as f:
            return json.load(f)
            
    def _save(self, data: List[Dict[str, Any]]):
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, 'w') as f:
            json.dump(data, f, indent=4)
            
    def register(self, definition: StrategyDefinition):
        data = self._load()
        # Remove old if exists
        data = [d for d in data if d["name"] != definition.name]
        data.append(definition.model_dump())
        self._save(data)
        
    def get_all(self) -> List[StrategyDefinition]:
        return [StrategyDefinition(**d) for d in self._load()]