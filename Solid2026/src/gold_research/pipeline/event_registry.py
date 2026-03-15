"""
Event Registry — active event state tracker for the ICT pipeline.

The EventRegistry maintains a dictionary of currently active IndicatorEvents,
keyed by their event_key().  Events enter the registry when state = ACTIVE,
and leave when a subsequent MITIGATED or EXPIRED event for the same key is
processed.

Design
------
The registry is a single-pass state machine fed by a chronologically-sorted
stream of IndicatorEvent objects (from the BarProcessor).  After processing
all events up to time T, the registry's get_active() method returns all
events that are "live" at T — i.e. formed and not yet consumed.

Thread safety: not designed for concurrent use (single-threaded backtesting).

Typical usage
-------------
    from gold_research.pipeline.event_registry import EventRegistry
    reg = EventRegistry()
    reg.feed(all_indicator_events)   # sorted by timestamp
    # then per-bar:
    active = reg.get_active_at(bar_ts)
    score  = reg.score_at(bar_ts)
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import pandas as pd

from gold_research.indicators.schema import (
    ConfluenceResult,
    Direction,
    EventState,
    EventType,
    IndicatorEvent,
)

# Event types that REMOVE a key from the active set
_TERMINATING_STATES = {EventState.MITIGATED, EventState.EXPIRED}

# Event types that ADD to the active set
_ACTIVATING_STATES = {EventState.ACTIVE, EventState.IN_ZONE}


class EventRegistry:
    """
    Tracks active IndicatorEvents across time for a single symbol.

    Parameters
    ----------
    symbol : str
        Instrument being tracked (informational only).
    max_event_age_bars : int | None
        If set, auto-expire events older than this many base-TF bars.
        None = no age limit (default).
    """

    def __init__(
        self,
        symbol: str = "XAUUSD",
        max_event_age_bars: Optional[int] = None,
    ) -> None:
        self.symbol             = symbol
        self.max_event_age_bars = max_event_age_bars

        # Active event store: key → IndicatorEvent
        self._active: Dict[str, IndicatorEvent] = {}

        # Full sorted event log (for time-travel queries)
        self._log: List[IndicatorEvent] = []

        # Internal cursor: index into _log up to which events have been applied
        self._cursor: int = 0

    # ── Ingestion ──────────────────────────────────────────────────────────────

    def feed(self, events: List[IndicatorEvent]) -> None:
        """
        Load a batch of indicator events.

        Events are merged into the internal log sorted by timestamp.
        Call advance_to() or get_active_at() to query the registry at any time.

        Parameters
        ----------
        events : List[IndicatorEvent]
            Need not be sorted; the registry sorts internally.
        """
        self._log.extend(events)
        self._log.sort(key=lambda e: e.timestamp)
        self._cursor = 0      # Reset cursor so queries start fresh
        self._active.clear()  # Clear active set (will be rebuilt on-demand)

    def advance_to(self, ts: pd.Timestamp) -> None:
        """
        Process all events with timestamp <= ts.

        Modifies the internal _active dict.
        """
        while self._cursor < len(self._log):
            evt = self._log[self._cursor]
            if evt.timestamp > ts:
                break
            self._apply(evt)
            self._cursor += 1

    def _apply(self, evt: IndicatorEvent) -> None:
        key = evt.event_key()
        if evt.state in _TERMINATING_STATES:
            self._active.pop(key, None)
        elif evt.state in _ACTIVATING_STATES:
            self._active[key] = evt
        # PENDING / EXPIRED without prior ACTIVE: ignore

    # ── Query ──────────────────────────────────────────────────────────────────

    def get_active_at(
        self,
        ts: pd.Timestamp,
        direction: Optional[Direction] = None,
        event_types: Optional[List[EventType]] = None,
    ) -> List[IndicatorEvent]:
        """
        Return all events active at timestamp ts.

        Parameters
        ----------
        ts : pd.Timestamp
        direction : Direction | None
            Filter by direction.  None = return all directions.
        event_types : list[EventType] | None
            Filter by event type.  None = return all types.
        """
        self.advance_to(ts)
        results = list(self._active.values())

        if direction is not None:
            results = [e for e in results if e.direction == direction]
        if event_types is not None:
            results = [e for e in results if e.event_type in event_types]

        return results

    def score_at(
        self,
        ts: pd.Timestamp,
        direction: Optional[Direction] = None,
    ) -> int:
        """Sum of score_contribution for all active events at ts."""
        return sum(e.score_contribution for e in self.get_active_at(ts, direction))

    def confluence_at(
        self,
        ts: pd.Timestamp,
        base_tf: str = "M15",
    ) -> ConfluenceResult:
        """
        Build a ConfluenceResult from all events active at ts.

        Parameters
        ----------
        ts : pd.Timestamp
        base_tf : str
            Base timeframe label (used for the ConfluenceResult header).
        """
        active = self.get_active_at(ts)
        return ConfluenceResult.from_events(ts, self.symbol, base_tf, active)

    def reset(self) -> None:
        """Clear all state.  Call before reprocessing the same log."""
        self._active.clear()
        self._cursor = 0

    def clear(self) -> None:
        """Clear all state AND the log."""
        self._active.clear()
        self._log.clear()
        self._cursor = 0

    def __len__(self) -> int:
        return len(self._active)

    def __repr__(self) -> str:
        return f"EventRegistry(symbol={self.symbol!r}, active={len(self._active)}, log={len(self._log)})"
