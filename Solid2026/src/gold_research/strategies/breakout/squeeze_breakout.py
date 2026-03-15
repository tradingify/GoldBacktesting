"""
Squeeze Breakout Strategy.

Hypothesis: Volatility cyclicity implies periods of extreme compression 
(Bollinger Bands fall inside Keltner Channels) lead to explosive directional 
expansions. Trading the break out of a squeeze catches the start of new momentum.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import SimpleMovingAverage, StandardDeviation, TrueRange
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit

class SqueezeSignal(SignalBase):
    def __init__(self, bb_period: int = 20, kc_period: int = 20, bb_mult: float = 2.0, kc_mult: float = 1.5):
        # BB Components
        self.bb_sma = SimpleMovingAverage(bb_period)
        self.bb_std = StandardDeviation(bb_period)
        self.bb_mult = bb_mult
        
        # KC Components
        self.kc_sma = SimpleMovingAverage(kc_period)
        self.tr = TrueRange(14) # ATR using Wilder or 14-period SMA
        self.kc_mult = kc_mult
        
        self.is_squeezed = False
        
    def update(self, bar: Bar):
         close = float(bar.close)
         self.bb_sma.add(close)
         self.bb_std.add(close)
         self.kc_sma.add(close)
         self.tr.add_bar(float(bar.high), float(bar.low), close)
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.bb_sma.is_ready or not self.bb_std.is_ready or not self.tr.is_ready:
            return None
            
        close = float(bar.close)
        atr = self.tr.atr
        
        # Calculate Bands
        bb_upper = self.bb_sma.value + (self.bb_mult * self.bb_std.value)
        bb_lower = self.bb_sma.value - (self.bb_mult * self.bb_std.value)
        
        kc_upper = self.kc_sma.value + (self.kc_mult * atr)
        kc_lower = self.kc_sma.value - (self.kc_mult * atr)
        
        # Squeeze Detection (BB completely inside KC)
        currently_squeezed = (bb_upper < kc_upper) and (bb_lower > kc_lower)
        
        # Release Trigger (Squeeze turns OFF, signifying expansion)
        if self.is_squeezed and not currently_squeezed:
            self.is_squeezed = currently_squeezed
            
            # Directional proxy: if close > BB sma
            if close > self.bb_sma.value:
                return SignalIntent(1, close, close - (1.5 * atr)) # Long Breakout
            else:
                return SignalIntent(-1, close, close + (1.5 * atr)) # Short Breakout
                
        # Maintain state
        self.is_squeezed = currently_squeezed
        return None

class SqueezeBreakoutConfig(GoldStrategyConfig):
    bb_period: int = 20
    kc_period: int = 20
    trail_atr_multiplier: float = 2.0

class SqueezeBreakout(GoldStrategy):
    
    def __init__(self, config: SqueezeBreakoutConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = SqueezeSignal(self.cfg.bb_period, self.cfg.kc_period)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)
        
        if self.is_invested:
             atr = self.signal_generator.tr.atr
             direction = 1 if self.is_long else -1
             self.exit_logic.update_trail(float(bar.close), atr, direction)