"""
ATR Breakout Strategy.

Hypothesis: Similar to Bollinger Band breakouts, an explosive move larger
than X * ATR from a baseline moving average indicates severe institutional
buying/selling that will establish a persistent trend.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import SimpleMovingAverage, TrueRange
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit

class ATRBreakoutSignal(SignalBase):
    def __init__(self, baseline_period: int, atr_threshold: float):
        self.baseline = SimpleMovingAverage(baseline_period)
        self.tr = TrueRange(14)
        self.atr_threshold = atr_threshold
        
    def update(self, bar: Bar):
         close = float(bar.close)
         self.baseline.add(close)
         self.tr.add_bar(float(bar.high), float(bar.low), close)
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.baseline.is_ready or not self.tr.is_ready:
            return None
            
        close = float(bar.close)
        baseline_val = self.baseline.value
        atr = self.tr.atr
        
        upper_band = baseline_val + (self.atr_threshold * atr)
        lower_band = baseline_val - (self.atr_threshold * atr)
        
        if close > upper_band:
            return SignalIntent(1, close, baseline_val) # Stop at baseline
        elif close < lower_band:
            return SignalIntent(-1, close, baseline_val)
            
        return None

class ATRBreakoutConfig(GoldStrategyConfig):
    baseline_period: int = 20
    atr_threshold: float = 2.0
    trail_atr_multiplier: float = 2.0

class ATRBreakout(GoldStrategy):
    
    def __init__(self, config: ATRBreakoutConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = ATRBreakoutSignal(self.cfg.baseline_period, self.cfg.atr_threshold)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)
        
        if self.is_invested:
             atr = self.signal_generator.tr.atr
             direction = 1 if self.is_long else -1
             self.exit_logic.update_trail(float(bar.close), atr, direction)