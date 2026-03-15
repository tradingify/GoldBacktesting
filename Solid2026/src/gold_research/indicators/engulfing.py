"""
Engulfing candle detector — research adapter.

Mirrors the logic of:
    D:\.openclaw\workspace-k\scripts\engulfing_pro_v1.py

Detects bullish and bearish engulfing patterns in two modes:

  "strict" : Current body fully contains previous body (classic definition).
  "smart"  : Current close extends beyond previous close, body size ≥ threshold.
             Open gap tolerance allows small gaps within body range.
             (Default — matches K's live reversal-hunting mode.)

Anti-lookahead guarantee
------------------------
Pattern uses only bar[i] (current) and bar[i-1] (previous).
Event timestamp = close of bar[i].

Parameters (defaults match live system)
----------------------------------------
mode           : "smart"  — engulfing detection mode.
req_color_swap : True     — require opposite candle colors.
body_size_mult : 0.8      — current body >= 80% of previous body.
gap_tolerance  : 0.5      — open gap tolerance as fraction of prev body.
"""

from __future__ import annotations

from typing import List, Literal

import numpy as np
import pandas as pd

from src.gold_research.indicators.schema import (
    Direction,
    EventState,
    EventType,
    IndicatorEvent,
    compute_score,
)

EngulfingMode = Literal["strict", "smart"]


def detect_engulfing(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    mode: EngulfingMode = "smart",
    req_color_swap: bool = True,
    body_size_mult: float = 0.8,
    gap_tolerance: float = 0.5,
) -> List[IndicatorEvent]:
    """
    Detect engulfing candles in a single-timeframe OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close.  DatetimeIndex (UTC).
    symbol : str
    timeframe : str
    mode : "strict" | "smart"
    req_color_swap : bool
    body_size_mult : float
        Current body must be >= body_size_mult × previous body.
    gap_tolerance : float
        Open gap allowed as fraction of previous body size (smart mode).

    Returns
    -------
    List[IndicatorEvent]
        ENGULFING events for each detected pattern.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    n      = len(df)
    opens  = df["open"].to_numpy(dtype=float)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    times  = df.index

    events: List[IndicatorEvent] = []

    for i in range(1, n):
        o_prev = opens[i - 1]
        c_prev = closes[i - 1]
        o_curr = opens[i]
        c_curr = closes[i]
        h_curr = highs[i]
        l_curr = lows[i]

        prev_body = abs(c_prev - o_prev)
        curr_body = abs(c_curr - o_curr)

        if prev_body == 0:
            continue

        # Color classification
        prev_bull = c_prev > o_prev
        curr_bull = c_curr > o_curr

        # Color swap requirement
        if req_color_swap and prev_bull == curr_bull:
            continue

        # Body size check
        if curr_body < body_size_mult * prev_body:
            continue

        # ── Bullish engulfing ─────────────────────────────────────────────────
        if curr_bull:
            if mode == "strict":
                engulfs = c_curr > c_prev and o_curr < o_prev
            else:  # smart
                gap_ok = o_curr >= o_prev - gap_tolerance * prev_body
                engulfs = c_curr > c_prev and gap_ok
            if engulfs:
                events.append(IndicatorEvent(
                    timestamp=times[i],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.BULLISH,
                    event_type=EventType.ENGULFING,
                    level_or_zone=float(c_curr),
                    state=EventState.ACTIVE,
                    metadata={
                        "mode": mode,
                        "prev_body": prev_body,
                        "curr_body": curr_body,
                        "prev_close": c_prev,
                    },
                    score_contribution=compute_score(EventType.ENGULFING, timeframe),
                ))

        # ── Bearish engulfing ─────────────────────────────────────────────────
        else:
            if mode == "strict":
                engulfs = c_curr < c_prev and o_curr > o_prev
            else:  # smart
                gap_ok = o_curr <= o_prev + gap_tolerance * prev_body
                engulfs = c_curr < c_prev and gap_ok
            if engulfs:
                events.append(IndicatorEvent(
                    timestamp=times[i],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.BEARISH,
                    event_type=EventType.ENGULFING,
                    level_or_zone=float(c_curr),
                    state=EventState.ACTIVE,
                    metadata={
                        "mode": mode,
                        "prev_body": prev_body,
                        "curr_body": curr_body,
                        "prev_close": c_prev,
                    },
                    score_contribution=compute_score(EventType.ENGULFING, timeframe),
                ))

    return events
