"""
Portfolio Level Risk Budgeting.

Gates execution at the strategy level by referencing total exposure metrics.
Provides the "Drawdown Derisking" behavior mentioned in the Master Plan docs.
"""
from typing import Dict, Any
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.config import load_yaml
from src.gold_research.core.logging import logger

class RiskBudgetController:
    """
    Supervises global limits defined in `risk.yaml` and enforces
    capital allocation gating (e.g., drawdown scaling).
    """
    
    def __init__(self):
        self.config = load_yaml(ProjectPaths.CONFIG_GLOBAL / "risk.yaml")
        
        # Maximum fraction of account lost before severe truncation.
        self.dd_threshold = float(self.config.get("drawdown_derisking", {}).get("threshold", 0.10))
        # The penalty multiplier applied to sizing after crossing threshold.
        self.dd_multiplier = float(self.config.get("drawdown_derisking", {}).get("multiplier", 0.50))
        
    def apply_drawdown_discount(self, initial_position_size: float, current_drawdown_pct: float) -> float:
        """
        Reduces leverage dynamically if the portfolio has crossed risk thresholds.
        
        Args:
            initial_position_size: Proposed trade size from PositionSizer.
            current_drawdown_pct: Portfolio total loss from High Water Mark (positive float, e.g. 0.05).
            
        Returns:
            Original or truncated position size.
        """
        if current_drawdown_pct >= self.dd_threshold:
            logger.warning(
                f"Drawdown {current_drawdown_pct*100:.1f}% exceeds threshold {self.dd_threshold*100:.1f}%. "
                f"Halving risk (Multiplier: {self.dd_multiplier}x)."
            )
            return initial_position_size * self.dd_multiplier
            
        return initial_position_size
