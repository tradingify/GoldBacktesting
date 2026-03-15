"""
Opening Range Breakout (ORB) Strategy.

Hypothesis: Institutional volume establishing positions at the open creates
a range. Breaking this initial range indicates the committed direction for
the rest of the session.
"""
from typing import Optional
import pandas as pd
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import FixedHoldTimeExit

class ORBSignal(SignalBase):
    def __init__(self, range_bars: int = 12):
        self.range_bars = range_bars
        self.current_day = None
        self.bars_in_session = 0
        self.range_high = float('-inf')
        self.range_low = float('inf')
        self.range_established = False
        self.traded_today = False
        
    def update(self, bar: Bar):
         dt = pd.to_datetime(bar.ts_event, unit="ns", utc=True)
         date_str = dt.strftime("%Y-%m-%d")
         
         if self.current_day is None or self.current_day != date_str:
             # New session reset
             self.current_day = date_str
             self.bars_in_session = 0
             self.range_high = float('-inf')
             self.range_low = float('inf')
             self.range_established = False
             self.traded_today = False
             
         high, low = float(bar.high), float(bar.low)
         
         if self.bars_in_session < self.range_bars:
             self.range_high = max(self.range_high, high)
             self.range_low = min(self.range_low, low)
             self.bars_in_session += 1
             
         if self.bars_in_session == self.range_bars:
             self.range_established = True
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.range_established or self.traded_today:
            return None
            
        close = float(bar.close)
        
        if close > self.range_high:
            self.traded_today = True
            return SignalIntent(1, close, self.range_low) # Stop logically at bottom of range
        elif close < self.range_low:
            self.traded_today = True
            return SignalIntent(-1, close, self.range_high)
            
        return None

class ORBConfig(GoldStrategyConfig):
    range_bars: int = 12 # First hour of 5m bars
    hold_bars: int = 72 # Rest of the day on 5m bars

class OpeningRangeBreakout(GoldStrategy):
    
    def __init__(self, config: ORBConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = ORBSignal(self.cfg.range_bars)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = FixedHoldTimeExit(self.cfg.hold_bars)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)