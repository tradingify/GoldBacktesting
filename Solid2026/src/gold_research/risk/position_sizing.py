"""
Position Sizing Module.

Dynamically evaluates trade sizes based on fixed fractional risk limits
and account stop-loss distances. Assumes strict adherence to the global
`risk.yaml` limits.
"""
from typing import Dict, Any, Optional
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.config import load_yaml
from src.gold_research.core.logging import logger

class PositionSizer:
    """Calculates strict fixed fractional position sizes."""
    
    def __init__(self, base_risk_pct: Optional[float] = None):
        """
        Args:
            base_risk_pct: The % of account risk permitted per trade. 
                           Defaults to risk.yaml if not provided. (e.g., 0.01 = 1%)
        """
        if base_risk_pct is None:
            config = load_yaml(ProjectPaths.CONFIG_GLOBAL / "risk.yaml")
            base_risk_pct = float(config.get("base_risk_per_trade", 0.01))
            
        self.base_risk_pct = base_risk_pct

    def calculate_size_from_stop(
        self, 
        account_equity: float, 
        entry_price: float, 
        stop_price: float,
        contract_multiplier: float = 1.0
    ) -> float:
        """
        Calculates trade size in contracts/lots using distance-to-stop.
        
        Formula: (Equity * Risk%) / (ABS(Entry - Stop) * Multiplier)
        
        Args:
            account_equity: T+0 Net Liquidation Value of the portfolio.
            entry_price: Target execution fill price.
            stop_price: Invalidation level where trade exits for a loss.
            contract_multiplier: Value of 1 point move (e.g., 100 for standard gold lots).
            
        Returns:
            Computed absolute position size.
            
        Raises:
            ValueError: If entry_price equals stop_price (infinite risk).
        """
        if entry_price == stop_price:
            logger.error("Stop price cannot equal entry price. Infinite sizing risk.")
            raise ValueError("Entry price == Stop price.")
            
        risk_capital = account_equity * self.base_risk_pct
        risk_per_unit = abs(entry_price - stop_price) * contract_multiplier
        
        if risk_per_unit == 0:
            return 0.0
            
        size = risk_capital / risk_per_unit
        
        # In a real environment, we'd floor this to the instrument's minimum lot step (e.g., 0.01)
        return size
