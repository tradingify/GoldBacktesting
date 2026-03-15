"""
Market Structure detector — research adapter.

Mirrors the logic of:
    D:\.openclaw\workspace\mtf-ob-build\market_structure_v1.py

Detects:
  BOS   — Break of Structure: close crosses beyond the last confirmed fractal
          pivot in the same trend direction (continuation).
  CHoCH — Change of Character: BOS occurs against the current trend bias
          (potential reversal signal).

Anti-lookahead guarantee
------------------------
Fractals require `length` confirmed bars on EACH side before they register.
A pivot at index p is not visible until bar index p + length (the last bar
in the confirmation window closes).  BOS/CHoCH event timestamp = close of
the bar that performs the break (index i), which is always > p + length.

Parameters (defaults match live system)
----------------------------------------
length : 5 — pivot window bars each side.  Fractal confirmed at i − length.
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from src.gold_research.indicators.schema import (
    Direction,
    EventState,
    EventType,
    IndicatorEvent,
    compute_score,
)


def detect_market_structure(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    length: int = 5,
) -> List[IndicatorEvent]:
    """
    Detect BOS and CHoCH events in a single-timeframe OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close.  DatetimeIndex (UTC).
    symbol : str
    timeframe : str
    length : int
        Fractal pivot window (bars each side).

    Returns
    -------
    List[IndicatorEvent]
        BOS and CHoCH events ordered by timestamp.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    n      = len(df)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    times  = df.index

    # ── Pivot detection ────────────────────────────────────────────────────────
    # pivot_high[i] = True if highs[i] is the unique max over [i-length, i+length]
    # Confirmation requires i + length < n (full right-side window available)
    pivot_highs = np.zeros(n, dtype=bool)
    pivot_lows  = np.zeros(n, dtype=bool)

    for i in range(length, n - length):
        window_h = highs[i - length : i + length + 1]
        window_l = lows [i - length : i + length + 1]
        if highs[i] == window_h.max() and (window_h == highs[i]).sum() == 1:
            pivot_highs[i] = True
        if lows[i]  == window_l.min() and (window_l == lows[i]).sum() == 1:
            pivot_lows[i]  = True

    # ── Trend state machine ────────────────────────────────────────────────────
    # 0 = undecided, 1 = bullish, -1 = bearish
    trend_state     = 0
    last_pivot_high = np.nan
    last_pivot_low  = np.nan

    events: List[IndicatorEvent] = []

    # Start scan after enough bars for a fully confirmed pivot
    for i in range(length * 2, n):
        # The pivot confirmed for this bar was at conf_idx = i - length
        conf_idx = i - length
        if conf_idx < length:
            continue

        if pivot_highs[conf_idx]:
            last_pivot_high = highs[conf_idx]
        if pivot_lows[conf_idx]:
            last_pivot_low = lows[conf_idx]

        if np.isnan(last_pivot_high) or np.isnan(last_pivot_low):
            continue

        bar_close = closes[i]
        bar_time  = times[i]

        if bar_close > last_pivot_high:
            etype = EventType.CHOCH if trend_state == -1 else EventType.BOS
            events.append(IndicatorEvent(
                timestamp=bar_time,
                symbol=symbol,
                timeframe=timeframe,
                direction=Direction.BULLISH,
                event_type=etype,
                level_or_zone=float(last_pivot_high),
                state=EventState.ACTIVE,
                metadata={
                    "broken_level": float(last_pivot_high),
                    "prev_trend":   trend_state,
                    "conf_idx":     int(conf_idx),
                },
                score_contribution=compute_score(etype, timeframe),
            ))
            trend_state     = 1
            # Advance reference level so next break is meaningful
            last_pivot_high = bar_close

        elif bar_close < last_pivot_low:
            etype = EventType.CHOCH if trend_state == 1 else EventType.BOS
            events.append(IndicatorEvent(
                timestamp=bar_time,
                symbol=symbol,
                timeframe=timeframe,
                direction=Direction.BEARISH,
                event_type=etype,
                level_or_zone=float(last_pivot_low),
                state=EventState.ACTIVE,
                metadata={
                    "broken_level": float(last_pivot_low),
                    "prev_trend":   trend_state,
                    "conf_idx":     int(conf_idx),
                },
                score_contribution=compute_score(etype, timeframe),
            ))
            trend_state    = -1
            last_pivot_low = bar_close

    return events
