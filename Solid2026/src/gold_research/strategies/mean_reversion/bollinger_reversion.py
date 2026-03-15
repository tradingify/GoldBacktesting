"""
Bollinger Band Reversion Strategy.

Hypothesis: Price overextensions past X standard deviations of a moving average
are unsustainable and will revert to the mean. Trading the bounds inward exploits
this elastic property.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import SimpleMovingAverage, StandardDeviation
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import FixedHoldTimeExit

class BollingerSignal(SignalBase):
    def __init__(self, period: int, std_devs: float):
        self.sma = SimpleMovingAverage(period)
        self.std = StandardDeviation(period)
        self.std_devs = std_devs
        
    def update(self, bar: Bar):
         close = float(bar.close)
         self.sma.add(close)
         self.std.add(close)
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.sma.is_ready or not self.std.is_ready:
            return None
            
        close = float(bar.close)
        baseline = self.sma.value
        band_width = self.std.value * self.std_devs
        
        upper_band = baseline + band_width
        lower_band = baseline - band_width
        
        # Risk stop hardcoded mathematically beyond the bands for safety mapping
        if close > upper_band:
            # Overbought -> Short reversion to baseline
            return SignalIntent(-1, close, upper_band + band_width) 
        elif close < lower_band:
            # Oversold -> Long reversion to baseline
            return SignalIntent(1, close, lower_band - band_width)
            
        return None

class BollingerReversionConfig(GoldStrategyConfig):
    period: int = 20
    std_devs: float = 2.0
    hold_bars: int = 5

class BollingerReversion(GoldStrategy):
    
    def __init__(self, config: BollingerReversionConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = BollingerSignal(self.cfg.period, self.cfg.std_devs)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = FixedHoldTimeExit(self.cfg.hold_bars)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)