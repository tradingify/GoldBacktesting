"""
Execution Cost Model.

Loads cost profiles (optimistic, base, harsh) from the global YAML configuration
and provides structured models representing commissions and spread edge cases.
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.config import load_yaml
from src.gold_research.core.enums import CostProfile

@dataclass
class ExecutionCost:
    """Represents the transactional friction of an execution profile."""
    commission_per_order: float
    spread: float
    slippage: float

class CostModelLoader:
    """
    Utility to load and instantiate cost profiles dynamically from config.
    """
    
    _cache: Optional[Dict[str, ExecutionCost]] = None
    
    @classmethod
    def load_profiles(cls) -> Dict[str, ExecutionCost]:
        """Loads all profiles from global costs.yaml."""
        if cls._cache is not None:
            return cls._cache
            
        profiles = {}
        config_path = ProjectPaths.CONFIG_GLOBAL / "costs.yaml"
        raw_config = load_yaml(config_path)
        
        for name, profile_dict in raw_config.items():
            profiles[name] = ExecutionCost(
                commission_per_order=float(profile_dict.get("commission_per_order", 0.0)),
                spread=float(profile_dict.get("spread", 0.0)),
                slippage=float(profile_dict.get("slippage", 0.0))
            )
            
        cls._cache = profiles
        return profiles

    @classmethod
    def get_profile(cls, profile: CostProfile) -> ExecutionCost:
        """Retrieves a specific cost profile."""
        profiles = cls.load_profiles()
        if profile.value not in profiles:
            raise ValueError(f"Cost profile '{profile.value}' not found in costs.yaml.")
        return profiles[profile.value]
