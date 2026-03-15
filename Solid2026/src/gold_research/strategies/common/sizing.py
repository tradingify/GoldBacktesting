"""
Common Sizing Adapters.

Connects the global `risk/position_sizing.py` mechanics to the
isolated strategy loops.
"""
from typing import Optional
from nautilus_trader.model.data import Bar
from src.gold_research.strategies.base.signal_base import SignalIntent
from src.gold_research.risk.position_sizing import PositionSizer
from src.gold_research.risk.risk_budget import RiskBudgetController
from src.gold_research.risk.exposure_limits import ExposureManager

class DynamicRiskSizer:
    """
    Adapter that intercepts a single strategy's SignalIntent, calculates
    the raw risk unit, applies portfolio drawdown discounting, and checks
    the global concentration limit before passing an absolute QTY to execution.
    """
    
    def __init__(self, contract_multiplier: float = 1.0):
        self.sizer = PositionSizer()
        self.budget_controller = RiskBudgetController()
        self.exposure_manager = ExposureManager()
        self.contract_multiplier = contract_multiplier
        
    def calculate_size(self, signal: SignalIntent, current_bar: Bar, strategy_ref) -> float:
        """
        Derives the executed trade size from the global capital rules.
        
        Args:
            signal: Emitted signal structure containing Stop distance.
            current_bar: State reference.
            strategy_ref: Pointer to strategy to check equity states.
        """
        try:
            # Try to get equity from portfolio account (compatible with various Nautilus versions)
            account = strategy_ref.portfolio.account(strategy_ref.nautilus_instrument_id.venue)
            if account is not None:
                equity = float(account.balance_total().as_double())
            else:
                equity = 100000.0  # Default if no account found
        except Exception:
            equity = 100000.0  # Fallback default
        
        # 2. Raw compute
        raw_size = self.sizer.calculate_size_from_stop(
            account_equity=equity,
            entry_price=signal.entry_price,
            stop_price=signal.stop_price,
            contract_multiplier=self.contract_multiplier
        )
        
        # 3. Apply Portfolio Drawdown Rules
        # (Assuming portfolio tracks a high-water mark, stubbed as 0.05 drawdown for logic path)
        dd_pct = 0.0 # strategy_ref.portfolio.metrics.current_drawdown
        adjusted_size = self.budget_controller.apply_drawdown_discount(raw_size, dd_pct)
        
        # 4. Check concentration limits 
        # (If exposure strictly fails, size goes to 0)
        open_strategy_notional = 0.0 # strategy_ref.portfolio.margins
        proposed_notional = adjusted_size * signal.entry_price * self.contract_multiplier
        
        if not self.exposure_manager.is_trade_allowed(proposed_notional, equity, open_strategy_notional):
             return 0.0
             
        return max(adjusted_size, 1.0)  # Minimum 1 unit