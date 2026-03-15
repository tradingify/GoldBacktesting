"""
EMA Cross Strategy.

Hypothesis: When a fast exponential moving average crosses over a slow EMA,
short-term momentum has shifted with greater recency-sensitivity than a pure SMA cross,
signalling a new trend lifecycle with faster reaction to price inflection points.

Structural mirror of MovingAverageCross but replaces SimpleMovingAverage with
ExponentialMovingAverage throughout.  All shared infrastructure (entry, exit,
sizing) is unchanged so the two strategies are directly comparable.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import ExponentialMovingAverage, TrueRange
from src.gold_research.strategies.common.helpers import crossover, crossunder
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit


class EMACrossSignal(SignalBase):
    """Crossover / crossunder signal generator using two EMAs."""

    def __init__(self, fast_period: int, slow_period: int):
        self.fast_ema = ExponentialMovingAverage(fast_period)
        self.slow_ema = ExponentialMovingAverage(slow_period)
        self.tr = TrueRange(14)

        self.fast_history: list = []
        self.slow_history: list = []

    def update(self, bar: Bar):
        close = float(bar.close)
        self.fast_ema.add(close)
        self.slow_ema.add(close)
        self.tr.add_bar(float(bar.high), float(bar.low), close)

        if self.fast_ema.is_ready and self.slow_ema.is_ready:
            self.fast_history.append(self.fast_ema.value)
            self.slow_history.append(self.slow_ema.value)

            # Keep only last 3 values for crossover detection
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


class EMACrossConfig(GoldStrategyConfig):
    fast_period: int = 9
    slow_period: int = 21
    trail_atr_multiplier: float = 2.0


class EMACross(GoldStrategy):

    def __init__(self, config: EMACrossConfig):
        super().__init__(config)
        self.cfg = config

    def setup_components(self):
        self.signal_generator = EMACrossSignal(self.cfg.fast_period, self.cfg.slow_period)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trail_atr_multiplier)
        self.position_sizer = DynamicRiskSizer()

    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)

        if self.is_invested:
            atr = self.signal_generator.tr.atr
            direction = 1 if self.is_long else -1
            self.exit_logic.update_trail(float(bar.close), atr, direction)
