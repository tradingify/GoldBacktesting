"""
Donchian Breakout Trend Strategy.

Hypothesis: Markets trading outside of their N-period historical highs/lows
are entering a directional momentum regime. Buying n-period highs captures
fat-tail trends.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import DonchianChannel, TrueRange
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit

class DonchianSignal(SignalBase):
    def __init__(self, lookback: int):
        self.donchian = DonchianChannel(lookback)
        self.tr = TrueRange(14)
        
    def update(self, bar: Bar):
         self.donchian.add_bar(float(bar.high), float(bar.low))
         self.tr.add_bar(float(bar.high), float(bar.low), float(bar.close))
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.donchian.is_ready or not self.tr.is_ready:
            return None
            
        close = float(bar.close)
        atr = self.tr.atr
        
        # 1 for Long, -1 for Short
        if close > self.donchian.upper:
            # Breakout Long. Stop loss 2 ATRs away.
            return SignalIntent(1, close, close - (2.0 * atr))
        elif close < self.donchian.lower:
            # Breakout Short.
            return SignalIntent(-1, close, close + (2.0 * atr))
            
        return None

class DonchianBreakoutConfig(GoldStrategyConfig):
    channel_lookback: int = 20
    trail_atr_multiplier: float = 3.0

class DonchianBreakout(GoldStrategy):
    
    def __init__(self, config: DonchianBreakoutConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = DonchianSignal(self.cfg.channel_lookback)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        # Push market data into signal generator's internal tracker
        self.signal_generator.update(bar)
        
        # If we have an open position, push ATR updates to the Trailing stop
        if self.is_invested:
             atr = self.signal_generator.tr.atr
             direction = 1 if self.is_long else -1
             self.exit_logic.update_trail(float(bar.close), atr, direction)