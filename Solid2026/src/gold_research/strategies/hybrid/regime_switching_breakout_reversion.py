"""
Regime Switching Hybrid Strategy.

Hypothesis: Trend-following models (Breakouts) underperform severely in choppy markets,
while Mean Reversion models get destroyed in strong trends. By identifying the market's
current volatility regime, we can selectively route signal logic to the correct model.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import StandardDeviation
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit

# Import existing signals
from src.gold_research.strategies.trend.donchian_breakout import DonchianSignal
from src.gold_research.strategies.mean_reversion.bollinger_reversion import BollingerSignal

class RegimeSwitchingSignal(SignalBase):
    def __init__(self, regime_lookback: int, donchian_period: int, bb_period: int):
        self.fast_vol = StandardDeviation(20)
        self.slow_vol = StandardDeviation(regime_lookback) # e.g. 100
        
        # Sub-modules
        self.trend_subsystem = DonchianSignal(donchian_period)
        self.reversion_subsystem = BollingerSignal(bb_period, 2.0)
        
    def update(self, bar: Bar):
         close = float(bar.close)
         self.fast_vol.add(close)
         self.slow_vol.add(close)
         
         # Feed data to both sub-systems constantly so they maintain state
         self.trend_subsystem.update(bar)
         self.reversion_subsystem.update(bar)
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if not self.fast_vol.is_ready or not self.slow_vol.is_ready:
            return None
            
        # Regime Identification
        # If short-term volatility is expanding past long-term average -> Momentum/Trend Regime
        is_trending_regime = self.fast_vol.value > self.slow_vol.value
        
        if is_trending_regime:
            # Route to Breakout logic
            return self.trend_subsystem.generate(bar)
        else:
            # Route to Mean Reversion logic inside chop
            return self.reversion_subsystem.generate(bar)

class HybridRegimeConfig(GoldStrategyConfig):
    regime_period: int = 100
    donchian_period: int = 20
    bb_period: int = 20
    trail_atr_multiplier: float = 2.0

class RegimeSwitchingBreakoutReversion(GoldStrategy):
    
    def __init__(self, config: HybridRegimeConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = RegimeSwitchingSignal(
            self.cfg.regime_period, 
            self.cfg.donchian_period, 
            self.cfg.bb_period
        )
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)
        
        if self.is_invested:
             atr = self.signal_generator.tr.atr
             direction = 1 if self.is_long else -1
             self.exit_logic.update_trail(float(bar.close), atr, direction)
