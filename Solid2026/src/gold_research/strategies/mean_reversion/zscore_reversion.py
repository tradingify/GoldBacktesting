"""
Z-Score Reversion Strategy.

Hypothesis: Statistical normalization of price (Current - Mean) / StdDev. 
When Z-Score exceeds a high magnitude (e.g. |z| > 2.5), it signifies an extreme
outlier probability event suitable for fading.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import SimpleMovingAverage, StandardDeviation, TrueRange
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit

class ZScoreSignal(SignalBase):
    def __init__(self, period: int, z_threshold: float):
        self.sma = SimpleMovingAverage(period)
        self.std = StandardDeviation(period)
        self.tr = TrueRange(14)
        self.z_threshold = z_threshold
        
    def update(self, bar: Bar):
         close = float(bar.close)
         self.sma.add(close)
         self.std.add(close)
         self.tr.add_bar(float(bar.high), float(bar.low), close)
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.sma.is_ready or not self.std.is_ready or not self.tr.is_ready:
            return None
            
        std_val = self.std.value
        if std_val == 0:
            return None
            
        close = float(bar.close)
        z_score = (close - self.sma.value) / std_val
        atr = self.tr.atr
        
        if z_score > self.z_threshold:
            # Overbought -> Short
            return SignalIntent(-1, close, close + (2.0 * atr))
        elif z_score < -self.z_threshold:
            # Oversold -> Long
            return SignalIntent(1, close, close - (2.0 * atr))
            
        return None

class ZScoreReversionConfig(GoldStrategyConfig):
    period: int = 30
    z_threshold: float = 2.5
    trail_atr_multiplier: float = 1.5

class ZScoreReversion(GoldStrategy):
    
    def __init__(self, config: ZScoreReversionConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = ZScoreSignal(self.cfg.period, self.cfg.z_threshold)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)
        
        if self.is_invested:
             atr = self.signal_generator.tr.atr
             direction = 1 if self.is_long else -1
             self.exit_logic.update_trail(float(bar.close), atr, direction)