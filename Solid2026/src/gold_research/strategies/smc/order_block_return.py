"""
SMC Order Block Return Strategy.
"""
from typing import Optional
import pandas as pd
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalIntent
from src.gold_research.strategies.smc.adapters import SMCSignalBase
from src.gold_research.indicators.order_blocks import detect_order_blocks
from src.gold_research.indicators.schema import EventState, Direction

from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit
from src.gold_research.strategies.common.sizing import DynamicRiskSizer


class OrderBlockReturnConfig(GoldStrategyConfig):
    window_size: int = 150
    disp_mult: float = 1.5
    swing_len: int = 10
    max_obs: int = 5
    max_touches: int = 2
    stop_atr_multiplier: float = 2.0
    trailing_stop_multiplier: float = 2.0


class OrderBlockSignal(SMCSignalBase):
    def __init__(self, config: OrderBlockReturnConfig):
        super().__init__(window_size=config.window_size, timeframe=config.timeframe)
        self.cfg = config
        
    def _evaluate_dataframe(self, df: pd.DataFrame, current_bar: Bar) -> Optional[SignalIntent]:
        events = detect_order_blocks(
            df=df,
            symbol="XAUUSD",
            timeframe=self.cfg.timeframe,
            disp_mult=self.cfg.disp_mult,
            swing_len=self.cfg.swing_len,
            max_obs=self.cfg.max_obs,
            max_touches=self.cfg.max_touches
        )
        
        if df.empty:
            return None
            
        # Parse the event stream to identify currently open OBs
        active_obs = {}
        for e in events:
            # We use direction and level as a unique key since order blocks 
            # don't overlap exactly with the same direction
            key = (e.direction, e.level_or_zone)
            if e.state == EventState.ACTIVE:
                active_obs[key] = e
            elif e.state in (EventState.MITIGATED, EventState.EXPIRED):
                active_obs.pop(key, None)
                
        # Now check if current close touches any active OB
        close = float(current_bar.close)
        for key, ob_event in active_obs.items():
            direction, (bot, top) = key
            
            if bot <= close <= top:
                atr = self.calc_atr(df)
                
                # We expect a reversal bounce out of the order block
                if direction == Direction.BULLISH:
                    stop_price = bot - (self.cfg.stop_atr_multiplier * atr)
                    return SignalIntent(1, close, stop_price, metadata={"ob_zone": ob_event.level_or_zone})
                else:
                    stop_price = top + (self.cfg.stop_atr_multiplier * atr)
                    return SignalIntent(-1, close, stop_price, metadata={"ob_zone": ob_event.level_or_zone})
                    
        return None
        
    def calc_atr(self, df: pd.DataFrame, period=14) -> float:
        if len(df) < period + 1:
            return 1.0
        high = df['high']
        low = df['low']
        close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])


class OrderBlockReturn(GoldStrategy):
    def __init__(self, config: OrderBlockReturnConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = OrderBlockSignal(self.cfg)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = TrailATRStopExit(self.cfg.trailing_stop_multiplier)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update_window(bar)
        
        if self.is_invested and self.signal_generator.rolling_window.is_ready:
            df = self.signal_generator.rolling_window.to_dataframe()
            atr = self.signal_generator.calc_atr(df)
            direction = 1 if self.is_long else -1
            self.exit_logic.update_trail(float(bar.close), atr, direction)
