"""
SMC Confluence Modular Strategy builder.

This strategy acts as a dynamic orchestration engine. It runs the ICT indicators
specified in `active_detectors` and aggregates them using the `ConfluenceResult` system.
Entries are triggered when the directional confluence score >= `min_fire_score`.

This allows testing ANY individual indicator alone (by setting active_detectors=["indicator"], 
and min_fire_score to its standard score), or ANY random combination of indicators.
"""
from typing import Optional, List, Tuple
import pandas as pd
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalIntent
from src.gold_research.strategies.smc.adapters import SMCSignalBase

from src.gold_research.indicators.schema import EventState, Direction, ConfluenceResult, IndicatorEvent
from src.gold_research.indicators.order_blocks import detect_order_blocks
from src.gold_research.indicators.fvg import detect_fvg
from src.gold_research.indicators.engulfing import detect_engulfing
from src.gold_research.indicators.market_structure import detect_market_structure
from src.gold_research.indicators.liquidity_pools import detect_liquidity
from src.gold_research.indicators.breaker_blocks import detect_breakers
from src.gold_research.indicators.ote import detect_ote
from src.gold_research.indicators.prev_high_low import detect_prev_hl
from src.gold_research.indicators.session_sweep import detect_session_sweeps

from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import TrailATRStopExit
from src.gold_research.strategies.common.sizing import DynamicRiskSizer


class ConfluenceScorerConfig(GoldStrategyConfig):
    window_size: int = 200
    stop_atr_multiplier: float = 2.0
    trailing_stop_multiplier: float = 2.0
    
    # Modular configuration parameters:
    active_detectors: Tuple[str, ...] = ("order_blocks", "fvg", "market_structure", "engulfing")
    min_fire_score: int = 6
    event_lookback: int = 20  # Bars to remember ephemeral events (BOS, Sweep, etc)


class ConfluenceSignal(SMCSignalBase):
    def __init__(self, config: ConfluenceScorerConfig):
        super().__init__(window_size=config.window_size, timeframe=config.timeframe)
        self.cfg = config
        
    def _evaluate_dataframe(self, df: pd.DataFrame, current_bar: Bar) -> Optional[SignalIntent]:
        if df.empty:
            return None
            
        latest_time = df.index[-1]
        close_price = float(current_bar.close)
        
        # 1. Run dynamic configured detectors
        all_events: List[IndicatorEvent] = []
        
        if "order_blocks" in self.cfg.active_detectors:
            all_events.extend(detect_order_blocks(df, timeframe=self.cfg.timeframe))
        if "fvg" in self.cfg.active_detectors:
            all_events.extend(detect_fvg(df, timeframe=self.cfg.timeframe))
        if "market_structure" in self.cfg.active_detectors:
            all_events.extend(detect_market_structure(df, timeframe=self.cfg.timeframe))
        if "engulfing" in self.cfg.active_detectors:
            all_events.extend(detect_engulfing(df, timeframe=self.cfg.timeframe))
        if "liquidity_pools" in self.cfg.active_detectors:
            all_events.extend(detect_liquidity(df, timeframe=self.cfg.timeframe))
        if "breaker_blocks" in self.cfg.active_detectors:
            all_events.extend(detect_breakers(df, timeframe=self.cfg.timeframe))
        if "ote" in self.cfg.active_detectors:
            all_events.extend(detect_ote(df, timeframe=self.cfg.timeframe))
        if "prev_high_low" in self.cfg.active_detectors:
            all_events.extend(detect_prev_hl(df, timeframe=self.cfg.timeframe))
        if "session_sweep" in self.cfg.active_detectors:
            all_events.extend(detect_session_sweeps(df, timeframe=self.cfg.timeframe))

        current_events: List[IndicatorEvent] = []
        lookback_cutoff = pd.Timestamp(latest_time) - self.get_lookback_timedelta(self.cfg.event_lookback)
        
        for e in all_events:
            # We accept events that happened on the current bar OR within the lookback window
            if pd.Timestamp(e.timestamp) >= lookback_cutoff:
                current_events.append(e)

        # 3. Unified state tracker for all active spatial zones (FVGs, OBs, OTE, Breakers) across history
        active_zones = {}
        for e in all_events:
            if isinstance(e.level_or_zone, (list, set)):
                loc = tuple(e.level_or_zone)
            else:
                loc = e.level_or_zone
                
            key = (e.event_type, e.direction, loc)
            
            if e.state == EventState.ACTIVE:
                active_zones[key] = e
            elif e.state in (EventState.MITIGATED, EventState.EXPIRED):
                active_zones.pop(key, None)
                
        # 4. Check if price is currently inside any of the remaining ACTIVE zones
        for key, event in active_zones.items():
            loc = event.level_or_zone
            if isinstance(loc, tuple) and len(loc) == 2:
                bot, top = loc
                if bot <= close_price <= top:
                    # Prevent duplicating the event if it happened to be formed exactly on the current bar
                    if event not in current_events:
                        current_events.append(event)
                
        if not current_events:
            return None
            
        # 5. Evaluate confluence of all present conditions
        result = ConfluenceResult.from_events(
            ts=latest_time,
            symbol="XAUUSD",
            base_tf=self.cfg.timeframe,
            events=current_events
        )
        
        # Temporary debug for first few bars with any score
        if not hasattr(self, "_dbg_count"): self._dbg_count = 0
        if 0 < result.total_score < 100 and self._dbg_count < 200:
             print(f"[DEBUG] BAR {latest_time}: Total={result.total_score}, Bull={result.bull_score}, Bear={result.bear_score}, Events={result.combo}")
             self._dbg_count += 1
             
        # 6. Fire Signal if dynamic score threshold is met
        if result.total_score >= self.cfg.min_fire_score and result.direction != Direction.NEUTRAL:
            atr = self.calc_atr(df)
            direction = 1 if result.direction == Direction.BULLISH else -1
            
            # Simple ATR-based protection
            stop_price = close_price - (direction * self.cfg.stop_atr_multiplier * atr)
            
            return SignalIntent(
                direction=direction,
                entry_price=close_price,
                stop_price=stop_price,
                metadata={
                    "confluence_score": result.total_score,
                    "confluence_combo": result.combo,
                    "detectors_used": ",".join(self.cfg.active_detectors)
                }
            )
            
        return None

    def get_lookback_timedelta(self, bars: int) -> pd.Timedelta:
        """Helper to convert bar count to timedelta for filtering."""
        tf = self.cfg.timeframe.lower()
        if "m" in tf:
            mins = int(tf.replace("m", ""))
            return pd.Timedelta(minutes=mins * bars)
        elif "h" in tf:
            hours = int(tf.replace("h", ""))
            return pd.Timedelta(hours=hours * bars)
        elif "d" in tf:
            days = int(tf.replace("d", ""))
            return pd.Timedelta(days=days * bars)
        return pd.Timedelta(minutes=15 * bars)
        
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


class ConfluenceScorerStrategy(GoldStrategy):
    def __init__(self, config: ConfluenceScorerConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = ConfluenceSignal(self.cfg)
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
            
    def evaluate_entries(self, bar: Bar):
        """
        Custom entry evaluation to handle SMC specific signal intents and initial stops.
        """
        if not self.signal_generator.rolling_window.is_ready:
            return
            
        # Signal Generation
        intent = self.signal_generator.generate(bar)
        
        # DEBUG
        if not hasattr(self, "_call_count"): self._call_count = 0
        if intent is not None and self._call_count < 20:
            print(f"[DEBUG] evaluate_entries CALLED with INTENT: {intent.direction} score={intent.metadata.get('confluence_score')}")
            self._call_count += 1
            
        if not intent:
            return
            
        # Determine Size
        qty = self.position_sizer.calculate_size(intent, bar, self)
        if qty <= 0:
            return
            
        # Execute Entry Mechanics
        if not hasattr(self, "_entry_count"): self._entry_count = 0
        if self._entry_count < 50:
            print(f"[DEBUG] EXECUTING ENTRY: {intent.direction} Qty={qty} Price={bar.close} Stop={intent.stop_price}")
            self._entry_count += 1
            
        self.entry_logic.execute(intent, qty, bar, self)
        
        # Set initial stop in trail module
        if hasattr(self, "exit_logic") and hasattr(self.exit_logic, 'set_initial_stop'):
             self.exit_logic.set_initial_stop(intent.stop_price)
             
    def on_order_filled(self, event):
        # Nautilus OrderFilled uses 'last_qty' for the amount filled in this event
        print(f"[DEBUG] ORDER FILLED: {event.instrument_id} Qty={event.last_qty}")
        
    def on_position_opened(self, event):
        print(f"[DEBUG] POSITION OPENED: {event.position_id}")
        
    def on_position_closed(self, event):
        print(f"[DEBUG] POSITION CLOSED: {event.position_id}")
