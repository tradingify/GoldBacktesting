"""
Previous High / Low Calculator — research adapter.

ICT concept: prior session / daily / weekly / monthly highs and lows act as
key reference levels.  Institutions use them as targets and as levels that,
once broken, confirm directional bias.

Supported timeframes:
  '1D' | 'D'        — previous calendar day
  '1W' | 'W'        — previous calendar week
  '1M' | 'M' | '1ME'— previous calendar month
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

_TF_MAP: dict[str, str] = {
    "1D":  "D",
    "D":   "D",
    "1W":  "W",
    "W":   "W",
    "1M":  "ME",
    "M":   "ME",
    "1ME": "ME",
}


def _resolve_freq(timeframe: str) -> str:
    key = timeframe.upper().strip()
    return _TF_MAP.get(key, timeframe)


def detect_prev_hl(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    target_tf: str = "1D",
) -> List[IndicatorEvent]:
    """
    Detect previous period high/low levels and when they are swept/broken.

    Parameters
    ----------
    df : pd.DataFrame
    symbol : str
    timeframe : str
        Data granularity (e.g., '15m').
    target_tf : str
        Target higher timeframe to calculate prev H/L for ('1D', '1W', '1M').

    Returns
    -------
    List[IndicatorEvent]
        PREV_HIGH_LOW_ACTIVE, PREV_HIGH_LOW_SWEPT events.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    freq = _resolve_freq(target_tf)
    highs = df["high"].values
    lows  = df["low"].values
    times = df.index

    # Assign each bar to a trading period label
    if freq == "D":
        period_label = df.index.date
    elif freq == "W":
        period_label = df.index.year * 100 + df.index.isocalendar().week.values
    elif freq == "ME":
        period_label = df.index.to_period("M")
    else:
        period_label = df.index.to_period(freq)

    period_df = pd.DataFrame({
        "high": highs,
        "low": lows,
        "period": period_label,
    }, index=df.index)

    period_stats = period_df.groupby("period").agg(
        period_high=("high", "max"),
        period_low=("low", "min"),
        first_bar=("high", lambda x: np.where(df.index == x.index[0])[0][0]), # Get int index of first bar
    )

    periods = period_stats.index.tolist()
    events: List[IndicatorEvent] = []

    for i in range(1, len(periods)):
        curr_p = periods[i]
        prev_p = periods[i - 1]

        prev_h = float(period_stats.loc[prev_p, "period_high"])
        prev_l = float(period_stats.loc[prev_p, "period_low"])
        
        # Start of current period
        start_idx = int(period_stats.loc[curr_p, "first_bar"])
        start_time = times[start_idx]

        # Limit scan to the current period's end
        end_idx = int(period_stats.loc[periods[i+1], "first_bar"]) if i + 1 < len(periods) else len(df)

        # 1. Emit Active Events at the open of the new period
        # Prev High represents resistance/BSL -> Bearish setup if swept (usually), or Bullish if broken.
        # Let's map sweeping a high to BEARISH (turtle soup), sweeping a low to BULLISH.
        
        events.append(IndicatorEvent(
            timestamp=start_time,
            symbol=symbol,
            timeframe=timeframe,
            direction=Direction.BEARISH, # High
            event_type=EventType.PREV_HIGH_LOW_ACTIVE,
            level_or_zone=prev_h,
            state=EventState.ACTIVE,
            metadata={"target_tf": target_tf, "type": "HIGH"},
            score_contribution=0
        ))
        
        events.append(IndicatorEvent(
            timestamp=start_time,
            symbol=symbol,
            timeframe=timeframe,
            direction=Direction.BULLISH, # Low
            event_type=EventType.PREV_HIGH_LOW_ACTIVE,
            level_or_zone=prev_l,
            state=EventState.ACTIVE,
            metadata={"target_tf": target_tf, "type": "LOW"},
            score_contribution=0
        ))

        # 2. Forward scan across the period for the sweeps/breaks
        high_swept = False
        low_swept = False

        for j in range(start_idx, end_idx):
            if not high_swept and highs[j] > prev_h:
                high_swept = True
                events.append(IndicatorEvent(
                    timestamp=times[j],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.BEARISH,
                    event_type=EventType.PREV_HIGH_LOW_SWEPT,
                    level_or_zone=prev_h,
                    state=EventState.MITIGATED,
                    metadata={"target_tf": target_tf, "type": "HIGH"},
                    score_contribution=compute_score(EventType.PREV_HIGH_LOW_SWEPT, timeframe)
                ))
                
            if not low_swept and lows[j] < prev_l:
                low_swept = True
                events.append(IndicatorEvent(
                    timestamp=times[j],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.BULLISH,
                    event_type=EventType.PREV_HIGH_LOW_SWEPT,
                    level_or_zone=prev_l,
                    state=EventState.MITIGATED,
                    metadata={"target_tf": target_tf, "type": "LOW"},
                    score_contribution=compute_score(EventType.PREV_HIGH_LOW_SWEPT, timeframe)
                ))
            
            if high_swept and low_swept:
                break # Both swept, stop scanning

    events.sort(key=lambda e: e.timestamp)
    return events
