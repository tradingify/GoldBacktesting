"""
Moving Average Cross Strategy.

Hypothesis: When a fast-moving average crosses over a slow-moving average,
short-term momentum has shifted to align with or overtake long-term momentum,
indicating a new trend lifecycle.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import SimpleMovingAverage, TrueRange
from src.gold_research.strategies.common.helpers import crossover, crossunder
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit

class MACrossSignal(SignalBase):
    def __init__(self, fast_period: int, slow_period: int):
        self.fast_ma = SimpleMovingAverage(fast_period)
        self.slow_ma = SimpleMovingAverage(slow_period)
        self.tr = TrueRange(14)
        
        self.fast_history = []
        self.slow_history = []
        
    def update(self, bar: Bar):
         close = float(bar.close)
         self.fast_ma.add(close)
         self.slow_ma.add(close)
         self.tr.add_bar(float(bar.high), float(bar.low), close)
         
         if self.fast_ma.is_ready and self.slow_ma.is_ready:
             self.fast_history.append(self.fast_ma.value)
             self.slow_history.append(self.slow_ma.value)
             
             # Keep history capped
             if len(self.fast_history) > 3:
                 self.fast_history.pop(0)
                 self.slow_history.pop(0)
                 
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.tr.is_ready or len(self.fast_history) < 2:
            return None
            
        close = float(bar.close)
        atr = self.tr.atr
        
        if crossover(self.fast_history, self.slow_history):
            return SignalIntent(1, close, close - (1.5 * atr))
        elif crossunder(self.fast_history, self.slow_history):
            return SignalIntent(-1, close, close + (1.5 * atr))
            
        return None

class MACrossConfig(GoldStrategyConfig):
    fast_period: int = 20
    slow_period: int = 50
    trail_atr_multiplier: float = 2.0

class MovingAverageCross(GoldStrategy):
    
    def __init__(self, config: MACrossConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = MACrossSignal(self.cfg.fast_period, self.cfg.slow_period)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)
        
        if self.is_invested:
             atr = self.signal_generator.tr.atr
             direction = 1 if self.is_long else -1
             self.exit_logic.update_trail(float(bar.close), atr, direction)
