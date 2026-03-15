"""
Exposure Limits Utility.

Guards against single-strategy concentration risks by checking existing
open leverage against `max_exposure_per_strategy`.
"""
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.config import load_yaml

class ExposureManager:
    """Manages limits to prevent overallocation."""
    
    def __init__(self):
        self.config = load_yaml(ProjectPaths.CONFIG_GLOBAL / "risk.yaml")
        strategy_cfg = self.config.get("strategy_sizing", {}).get("fixed_fractional", {})
        portfolio_cfg = self.config.get("portfolio", {})
        self.max_strategy_exposure = float(
            self.config.get(
                "max_exposure_per_strategy",
                strategy_cfg.get("max_exposure_per_strategy", 0.05),
            )
        )
        self.max_portfolio_risk = float(
            self.config.get(
                "max_portfolio_risk",
                portfolio_cfg.get("max_portfolio_risk", 0.10),
            )
        )
        
    def is_trade_allowed(self, proposed_size_notional: float, current_equity: float, open_strategy_notional: float) -> bool:
        """
        Gatekeeper boolean for approving strategy signaling based on maximum allocations.
        
        Args:
            proposed_size_notional: Cash value of the new trade intent.
            current_equity: Total Net Liq.
            open_strategy_notional: Sum of cash value already engaged in this specific strategy.
            
        Returns:
            True if the trade fits inside the 5% margin budget allocation.
        """
        if current_equity <= 0:
            return False

        projected_exposure = (open_strategy_notional + proposed_size_notional) / current_equity
        return projected_exposure <= self.max_strategy_exposure
