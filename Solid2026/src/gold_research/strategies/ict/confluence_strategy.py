"""
ICT Confluence Strategy — NautilusTrader-native implementation.

This strategy runs the full ICT indicator pipeline on every incoming bar and
fires a trade entry when the confluence score meets or exceeds MIN_FIRE_SCORE.

It mirrors the logic of K's live system (k_scanner_v2.py + confluence_scorer.py)
adapted for offline backtesting on NautilusTrader.

Architecture
------------
  For each base-TF bar close:
    1. Update all single-TF indicator state machines (incremental, stateful).
    2. Query EventRegistry for current active events.
    3. Compute ConfluenceResult.
    4. If fire=True and no open position: submit market entry.
    5. Monitor open position for TP/SL exit.

Indicator data note
-------------------
Higher-TF indicators (H1, H4, D1) require their respective bar data.
In NautilusTrader backtesting, we subscribe to all required timeframe bars
and maintain per-TF indicator state machines.  Each higher-TF bar close
triggers an indicator update on that TF's data before the base-TF bars
for that period are processed.

For a simpler research-first approach, this strategy calls the vectorized
BarProcessor as a warm-up step on historical data, then transitions to
incremental bar-by-bar updates for the live/backtesting period.

Entry / Exit
------------
  Entry : Market order at bar close when fire=True.
  Stop  : ATR-based below/above the triggering bar's low/high.
  TP    : Fixed risk:reward from the SCORE_MATRIX-weighted ATR stop.

Config parameters
-----------------
  rr              : 2.0    — take-profit R:R.
  atr_window      : 14     — ATR period for stop sizing.
  atr_sl_mult     : 1.0    — stop = atr_sl_mult × ATR from entry.
  min_fire_score  : 6      — confluence threshold (matches live system).
  base_tf_minutes : 15     — base timeframe in minutes.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.position import Position

from gold_research.indicators.schema import (
    Direction,
    MIN_FIRE_SCORE,
    ConfluenceResult,
)
from gold_research.pipeline.event_registry import EventRegistry
from gold_research.strategies.base.exit_base import ExitBase
from gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from gold_research.strategies.common.entries import MarketEntryExecutor
from gold_research.strategies.common.indicators import TrueRange
from gold_research.strategies.common.sizing import DynamicRiskSizer
from gold_research.strategies.session.asia_session_sweep import FixedRRTPSLExit


# ── ATR Stop / TP Exit ────────────────────────────────────────────────────────

class ATRStopExit(ExitBase):
    """
    ATR-based fixed-RR exit.

    Stop = atr_mult × current ATR below (long) / above (short) entry.
    TP   = entry ± rr × risk.
    """

    def __init__(self, rr: float = 2.0, atr_window: int = 14, atr_mult: float = 1.0) -> None:
        self.rr        = rr
        self.atr_mult  = atr_mult
        self._atr      = TrueRange(atr_window)
        self.sl_level: Optional[float] = None
        self.tp_level: Optional[float] = None
        self.direction: Optional[int]  = None

    def arm(self, entry: float, atr: float, direction: int) -> None:
        risk          = self.atr_mult * atr
        self.direction = direction
        self.sl_level  = entry - risk if direction == 1 else entry + risk
        self.tp_level  = entry + self.rr * risk if direction == 1 else entry - self.rr * risk

    def disarm(self) -> None:
        self.sl_level = None
        self.tp_level = None
        self.direction = None

    def should_exit(self, bar: Bar, position: Optional[Position] = None) -> bool:
        if self.sl_level is None or position is None:
            return False
        hi = float(bar.high)
        lo = float(bar.low)
        if self.direction == 1:
            if lo <= self.sl_level or hi >= self.tp_level:
                self.disarm()
                return True
        else:
            if hi >= self.sl_level or lo <= self.tp_level:
                self.disarm()
                return True
        return False


# ── Confluence Signal ─────────────────────────────────────────────────────────

class ICTConfluenceSignal(SignalBase):
    """
    Bar-by-bar signal generator backed by the EventRegistry.

    For the backtesting research flow, the registry is pre-populated with
    all indicator events from the vectorized pipeline.  The signal generator
    simply queries it at each bar timestamp.

    Parameters
    ----------
    registry : EventRegistry
        Pre-populated registry (from BarProcessor.run()).
    min_fire_score : int
        Minimum total score to fire.  Default = MIN_FIRE_SCORE (6).
    """

    def __init__(
        self,
        registry: EventRegistry,
        min_fire_score: int = MIN_FIRE_SCORE,
        atr_window: int = 14,
        atr_mult: float = 1.0,
    ) -> None:
        self.registry       = registry
        self.min_fire_score = min_fire_score
        self.atr_window     = atr_window
        self.atr_mult       = atr_mult
        self._atr           = TrueRange(atr_window)
        self._last_atr: float = 0.0

    def update(self, bar: Bar) -> None:
        self._atr.update(bar)
        if self._atr.is_ready:
            self._last_atr = self._atr.value

    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        if self._last_atr == 0:
            return None

        ts = pd.to_datetime(bar.ts_event, unit="ns", utc=True)
        result: ConfluenceResult = self.registry.confluence_at(ts)

        if not result.fire:
            return None

        direction   = 1 if result.direction == Direction.BULLISH else -1
        entry_price = float(bar.close)
        risk        = self.atr_mult * self._last_atr
        stop_price  = (
            entry_price - risk if direction == 1
            else entry_price + risk
        )

        return SignalIntent(
            direction=direction,
            entry_price=entry_price,
            stop_price=stop_price,
            metadata={
                "score":     result.total_score,
                "combo":     result.combo,
                "n_events":  len(result.active_events),
                "direction": result.direction.value,
            },
        )


# ── Config & Strategy ─────────────────────────────────────────────────────────

class ICTConfluenceConfig(GoldStrategyConfig):
    rr:             float = 2.0
    atr_window:     int   = 14
    atr_sl_mult:    float = 1.0
    min_fire_score: int   = MIN_FIRE_SCORE


class ICTConfluenceStrategy(GoldStrategy):
    """
    ICT Confluence Strategy — NautilusTrader-native.

    Entry when confluence score >= min_fire_score (default 6).
    Exit via ATR-based fixed RR stop/take-profit.

    Usage in research
    -----------------
    This strategy is instantiated by a runner script that:
      1. Calls BarProcessor.run() to pre-compute the event registry.
      2. Passes the populated EventRegistry to ICTConfluenceSignal.
      3. Runs the NautilusTrader BacktestNode.

    Example runner: scripts/run_ict_event_pipeline.py
    """

    def __init__(self, config: ICTConfluenceConfig, registry: EventRegistry) -> None:
        super().__init__(config)
        self.cfg      = config
        self.registry = registry

    def setup_components(self) -> None:
        self.signal_generator = ICTConfluenceSignal(
            registry=self.registry,
            min_fire_score=self.cfg.min_fire_score,
            atr_window=self.cfg.atr_window,
            atr_mult=self.cfg.atr_sl_mult,
        )
        self.entry_logic      = MarketEntryExecutor()
        self.exit_logic       = FixedRRTPSLExit(self.cfg.rr)
        self.position_sizer   = DynamicRiskSizer()

    def update_state(self, bar: Bar) -> None:
        self.signal_generator.update(bar)

    def evaluate_entries(self, bar: Bar) -> None:
        if self.regime_filter and not self.regime_filter.is_active(bar):
            return

        signal = self.signal_generator.generate(bar)
        if signal is None:
            return

        qty = 1.0
        if self.position_sizer:
            qty = self.position_sizer.calculate_size(signal, bar, self)

        if self.entry_logic:
            self.entry_logic.execute(signal, qty, bar, self)
            risk = self.cfg.atr_sl_mult * float(self.signal_generator._last_atr)
            rr_risk = risk  # Fixed RR from config
            self.exit_logic.arm(
                signal.entry_price,
                signal.stop_price,
                signal.direction,
            )
