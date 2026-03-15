"""
Fair Value Gap (FVG) detector — research adapter.

Mirrors the logic of:
    D:\.openclaw\workspace-k\tools\indicators\fvg_detector.py

An FVG is a 3-candle imbalance where there is no price overlap between
bar[i-1] and bar[i+1]:

  Bullish FVG : bar[i-1].high < bar[i+1].low   (gap above middle bar)
  Bearish FVG : bar[i-1].low  > bar[i+1].high  (gap below middle bar)

The gap (FVG zone) is:
  Bullish : (bar[i-1].high, bar[i+1].low)
  Bearish : (bar[i+1].high, bar[i-1].low)

Anti-lookahead guarantee
------------------------
FVG_FORMED event timestamp = close of bar[i+1] (earliest the full gap is
confirmed).  Mitigation check starts at bar[i+2].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from src.gold_research.indicators.schema import (
    Direction,
    EventState,
    EventType,
    IndicatorEvent,
    compute_score,
)


@dataclass
class _FVGRecord:
    direction:      int          # 1 = bullish, -1 = bearish
    top:            float
    bottom:         float
    formed_time:    pd.Timestamp
    bar_idx:        int
    active:         bool = True
    mitigated:      bool = False
    mitigated_time: Optional[pd.Timestamp] = None


def detect_fvg(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    join_consecutive: bool = True,
    join_gap_bars: int = 4,
) -> List[IndicatorEvent]:
    """
    Detect Fair Value Gaps in a single-timeframe OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close.  DatetimeIndex (UTC).
    symbol : str
    timeframe : str
    join_consecutive : bool
        Merge adjacent same-direction FVGs with overlapping ranges
        (within join_gap_bars bars of each other).
    join_gap_bars : int
        Max bar gap for consecutive FVG merging.

    Returns
    -------
    List[IndicatorEvent]
        FVG_ACTIVE events (formed) and FVG_MITIGATED events.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    n      = len(df)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    times  = df.index

    raw_fvgs: List[_FVGRecord] = []

    # Detect raw FVGs (need i-1, i, i+1 → start at i=1, end at n-2)
    for i in range(1, n - 1):
        # Bullish FVG
        if highs[i - 1] < lows[i + 1]:
            raw_fvgs.append(_FVGRecord(
                direction=1,
                top=lows[i + 1],
                bottom=highs[i - 1],
                formed_time=times[i + 1],
                bar_idx=i + 1,
            ))
        # Bearish FVG
        elif lows[i - 1] > highs[i + 1]:
            raw_fvgs.append(_FVGRecord(
                direction=-1,
                top=lows[i - 1],
                bottom=highs[i + 1],
                formed_time=times[i + 1],
                bar_idx=i + 1,
            ))

    if not raw_fvgs:
        return []

    # Optional: merge consecutive same-direction FVGs
    if join_consecutive:
        raw_fvgs = _merge_consecutive(raw_fvgs, join_gap_bars)

    # Scan for mitigation (forward from bar_idx + 1)
    events: List[IndicatorEvent] = []

    for fvg in raw_fvgs:
        direction = Direction.BULLISH if fvg.direction == 1 else Direction.BEARISH
        score     = compute_score(EventType.FVG_ACTIVE, timeframe)

        # Emit ACTIVE event at formation time
        events.append(IndicatorEvent(
            timestamp=fvg.formed_time,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            event_type=EventType.FVG_ACTIVE,
            level_or_zone=(fvg.bottom, fvg.top),
            state=EventState.ACTIVE,
            metadata={"bar_idx": fvg.bar_idx},
            score_contribution=score,
        ))

        # Scan for mitigation (price enters the gap zone)
        for j in range(fvg.bar_idx + 1, n):
            # Mitigation: bar enters the gap zone (low <= top AND high >= bottom)
            if lows[j] <= fvg.top and highs[j] >= fvg.bottom:
                fvg.active        = False
                fvg.mitigated     = True
                fvg.mitigated_time = times[j]
                events.append(IndicatorEvent(
                    timestamp=times[j],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=direction,
                    event_type=EventType.FVG_MITIGATED,
                    level_or_zone=(fvg.bottom, fvg.top),
                    state=EventState.MITIGATED,
                    metadata={"bar_idx": fvg.bar_idx, "mitigated_bar": j},
                    score_contribution=0,
                ))
                break

    return events


def _merge_consecutive(fvgs: List[_FVGRecord], gap_bars: int) -> List[_FVGRecord]:
    """Merge adjacent same-direction FVGs with overlapping zones."""
    if not fvgs:
        return fvgs

    merged: List[_FVGRecord] = []
    current = fvgs[0]

    for nxt in fvgs[1:]:
        if (
            nxt.direction == current.direction
            and (nxt.bar_idx - current.bar_idx) <= gap_bars
            and nxt.bottom <= current.top  # Overlapping zones
        ):
            # Extend current FVG zone
            current = _FVGRecord(
                direction=current.direction,
                top=max(current.top, nxt.top),
                bottom=min(current.bottom, nxt.bottom),
                formed_time=current.formed_time,
                bar_idx=current.bar_idx,
            )
        else:
            merged.append(current)
            current = nxt

    merged.append(current)
    return merged
