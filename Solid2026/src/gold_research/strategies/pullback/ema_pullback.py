"""
EMA Pullback Strategy.

Hypothesis: In established trends, price retracements to a medium-term moving 
average represent "value" buying/selling opportunities as institutional algorithms
defend the average cost basis.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import ExponentialMovingAverage, TrueRange
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit

class EMAPullbackSignal(SignalBase):
    def __init__(self, fast_ema_period: int, slow_ema_period: int, pullback_threshold_pct: float = 0.001):
        self.fast_ema = ExponentialMovingAverage(fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(slow_ema_period)
        self.tr = TrueRange(14)
        self.pullback_threshold_pct = pullback_threshold_pct
        
    def update(self, bar: Bar):
         close = float(bar.close)
         self.fast_ema.add(close)
         self.slow_ema.add(close)
         self.tr.add_bar(float(bar.high), float(bar.low), close)
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.fast_ema.is_ready or not self.slow_ema.is_ready or not self.tr.is_ready:
            return None
            
        close = float(bar.close)
        low = float(bar.low)
        high = float(bar.high)
        fast_val = self.fast_ema.value
        slow_val = self.slow_ema.value
        atr = self.tr.atr
        
        # Trend Definition: Fast > Slow EMA
        is_uptrend = fast_val > slow_val
        is_downtrend = fast_val < slow_val
        
        # Pullback Zone defined around the Fast EMA
        zone_distance = close * self.pullback_threshold_pct
        
        if is_uptrend and (low <= fast_val + zone_distance) and (close >= fast_val):
            # Price dipped into/near the Fast EMA and closed above it -> Buy Pullback
            return SignalIntent(1, close, slow_val) # Stop beneath slow EMA structurally
            
        elif is_downtrend and (high >= fast_val - zone_distance) and (close <= fast_val):
            # Price spiked into/near the Fast EMA and closed below it -> Sell Pullback
            return SignalIntent(-1, close, slow_val) # Stop above slow EMA
            
        return None

class EMAPullbackConfig(GoldStrategyConfig):
    fast_period: int = 21
    slow_period: int = 50
    pullback_tolerance: float = 0.0005 # 5 basis points
    trail_atr_multiplier: float = 1.5

class EMAPullback(GoldStrategy):
    
    def __init__(self, config: EMAPullbackConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = EMAPullbackSignal(self.cfg.fast_period, self.cfg.slow_period, self.cfg.pullback_tolerance)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)
        
        if self.is_invested:
             atr = self.signal_generator.tr.atr
             direction = 1 if self.is_long else -1
             self.exit_logic.update_trail(float(bar.close), atr, direction)