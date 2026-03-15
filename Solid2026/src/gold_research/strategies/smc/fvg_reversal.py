"""
SMC FVG Reversal Strategy.
"""
from typing import Optional
import pandas as pd
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalIntent
from src.gold_research.strategies.smc.adapters import SMCSignalBase
from src.gold_research.indicators.fvg import detect_fvg
from src.gold_research.indicators.schema import EventType, Direction

from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit
from src.gold_research.strategies.common.sizing import DynamicRiskSizer


class FVGReversalConfig(GoldStrategyConfig):
    window_size: int = 150
    join_consecutive: bool = True
    join_gap_bars: int = 4
    stop_atr_multiplier: float = 2.0
    trailing_stop_multiplier: float = 2.0


class FVGReversalSignal(SMCSignalBase):
    def __init__(self, config: FVGReversalConfig):
        super().__init__(window_size=config.window_size, timeframe=config.timeframe)
        self.cfg = config
        
    def _evaluate_dataframe(self, df: pd.DataFrame, current_bar: Bar) -> Optional[SignalIntent]:
        events = detect_fvg(
            df=df,
            symbol="XAUUSD", # Canonical instrument
            timeframe=self.cfg.timeframe,
            join_consecutive=self.cfg.join_consecutive,
            join_gap_bars=self.cfg.join_gap_bars
        )
        
        if df.empty:
            return None
        
        latest_time = df.index[-1]
        
        for e in events:
            # We look for a mitigation event that occurs on exactly the last bar of the window
            if e.event_type == EventType.FVG_MITIGATED and e.timestamp == latest_time:
                close = float(current_bar.close)
                fvg_bot, fvg_top = e.level_or_zone
                atr = self.calc_atr(df)
                
                if e.direction == Direction.BULLISH:
                    stop_price = fvg_bot - (self.cfg.stop_atr_multiplier * atr)
                    return SignalIntent(1, close, stop_price, metadata={"fvg_zone": e.level_or_zone})
                else:
                    stop_price = fvg_top + (self.cfg.stop_atr_multiplier * atr)
                    return SignalIntent(-1, close, stop_price, metadata={"fvg_zone": e.level_or_zone})
        return None
        
    def calc_atr(self, df: pd.DataFrame, period=14) -> float:
        if len(df) < period + 1:
            return 1.0 # default fallback
        high = df['high']
        low = df['low']
        close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])


class FVGReversal(GoldStrategy):
    def __init__(self, config: FVGReversalConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = FVGReversalSignal(self.cfg)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trailing_stop_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        # 1. Update the rolling window 
        self.signal_generator.update_window(bar)
        
        # 2. Update trailing stop if we hold a position
        if self.is_invested and self.signal_generator.rolling_window.is_ready:
            df = self.signal_generator.rolling_window.to_dataframe()
            atr = self.signal_generator.calc_atr(df)
            direction = 1 if self.is_long else -1
            self.exit_logic.update_trail(float(bar.close), atr, direction)
