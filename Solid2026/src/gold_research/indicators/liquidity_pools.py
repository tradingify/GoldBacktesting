"""
Liquidity Pools Detector — research adapter.

ICT concept: clustered swing highs = buyside liquidity (BSL).
             clustered swing lows  = sellside liquidity (SSL).

Institutions hunt these pools before reversals; tracking them reveals
likely price targets for sweeps.

Detection pipeline:
  1. Find all N-bar pivot highs/lows.
  2. Cluster those within range_percent of each other → one pool per cluster.
  3. Pool is "swept" when price closes beyond it.

Anti-lookahead guarantee
------------------------
A swing high/low at index p is confirmed at index p + swing_length.
A pool cluster is formed / active on the confirmation bar of its *last* 
constituent pivot (end_bar + swing_length).
Sweeps are scanned strictly after pool formation.
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


def _find_swings(highs: np.ndarray, lows: np.ndarray, length: int):
    """Return sorted lists of bar indices that are confirmed swing H/L."""
    n      = len(highs)
    sh_idx = []
    sl_idx = []

    for i in range(length, n - length):
        win_h = highs[i - length : i + length + 1]
        win_l = lows [i - length : i + length + 1]

        # strict pivot: no tie allowed at the pivot bar itself vs neighbours
        if (highs[i] == win_h.max()
                and highs[i] > highs[i - 1]
                and highs[i] > highs[i + 1]):
            sh_idx.append(i)

        if (lows[i] == win_l.min()
                and lows[i] < lows[i - 1]
                and lows[i] < lows[i + 1]):
            sl_idx.append(i)

    return sh_idx, sl_idx


def _cluster(swing_bars: list[int], prices: np.ndarray, range_pct: float) -> list[dict]:
    """Group swing levels within range_pct of each other into pools."""
    if not swing_bars:
        return []

    levels   = [float(prices[b]) for b in swing_bars]
    used     = [False] * len(levels)
    clusters = []

    for i in range(len(levels)):
        if used[i]:
            continue
        g_bars   = [swing_bars[i]]
        g_levels = [levels[i]]
        used[i]  = True

        for j in range(i + 1, len(levels)):
            if used[j]:
                continue
            if abs(levels[j] - levels[i]) / max(levels[i], 1e-10) <= range_pct:
                g_bars.append(swing_bars[j])
                g_levels.append(levels[j])
                used[j] = True

        clusters.append({
            "level":       float(np.mean(g_levels)),
            "start_bar":   min(g_bars),
            "end_bar":     max(g_bars),
            "swing_count": len(g_bars),
        })

    return clusters


def detect_liquidity(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    swing_length: int = 10,
    range_percent: float = 0.01,
) -> List[IndicatorEvent]:
    """
    Detect buyside (BSL) and sellside (SSL) liquidity pools and sweeps.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close.
    symbol : str
    timeframe : str
    swing_length : int
        Bars each side required to confirm a swing H/L.
    range_percent : float
        Fractional price tolerance for clustering (0.01 = 1 %).

    Returns
    -------
    List[IndicatorEvent]
        LIQUIDITY_POOL_FORMED and LIQUIDITY_POOL_SWEPT events.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    times  = df.index
    n      = len(df)

    sh_bars, sl_bars = _find_swings(highs, lows, swing_length)

    bsl_clusters = _cluster(sh_bars, highs, range_percent)
    ssl_clusters = _cluster(sl_bars, lows,  range_percent)

    events: List[IndicatorEvent] = []

    # 1. Buyside Liquidity (BSL) targetting highs (bullish level to break, but acts bearish on full reversal normally)
    for c in bsl_clusters:
        level = c["level"]
        conf_idx = c["end_bar"] + swing_length
        if conf_idx >= n:
            continue
            
        formed_time = times[conf_idx]
        
        # BSL represents supply side / bearish reversal zone typically
        events.append(IndicatorEvent(
            timestamp=formed_time,
            symbol=symbol,
            timeframe=timeframe,
            direction=Direction.BEARISH, # A BSL sweep is often a bearish setup (turtle soup)
            event_type=EventType.LIQUIDITY_POOL_FORMED,
            level_or_zone=level,
            state=EventState.ACTIVE,
            metadata={"swing_count": c["swing_count"], "pool_type": "BSL"},
            score_contribution=0
        ))

        # Sweep occurs if price closes above the clustered high
        for j in range(conf_idx + 1, n):
            if closes[j] > level:
                events.append(IndicatorEvent(
                    timestamp=times[j],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.BEARISH, # Taking out BSL offers a short entry
                    event_type=EventType.LIQUIDITY_POOL_SWEPT,
                    level_or_zone=level,
                    state=EventState.MITIGATED,
                    metadata={"swing_count": c["swing_count"], "pool_type": "BSL"},
                    score_contribution=compute_score(EventType.LIQUIDITY_POOL_SWEPT, timeframe)
                ))
                break

    # 2. Sellside Liquidity (SSL) targetting lows
    for c in ssl_clusters:
        level = c["level"]
        conf_idx = c["end_bar"] + swing_length
        if conf_idx >= n:
            continue
            
        formed_time = times[conf_idx]
        
        events.append(IndicatorEvent(
            timestamp=formed_time,
            symbol=symbol,
            timeframe=timeframe,
            direction=Direction.BULLISH, # SSL sweep is often a bullish setup
            event_type=EventType.LIQUIDITY_POOL_FORMED,
            level_or_zone=level,
            state=EventState.ACTIVE,
            metadata={"swing_count": c["swing_count"], "pool_type": "SSL"},
            score_contribution=0
        ))

        for j in range(conf_idx + 1, n):
            if closes[j] < level:
                events.append(IndicatorEvent(
                    timestamp=times[j],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.BULLISH,
                    event_type=EventType.LIQUIDITY_POOL_SWEPT,
                    level_or_zone=level,
                    state=EventState.MITIGATED,
                    metadata={"swing_count": c["swing_count"], "pool_type": "SSL"},
                    score_contribution=compute_score(EventType.LIQUIDITY_POOL_SWEPT, timeframe)
                ))
                break

    events.sort(key=lambda e: e.timestamp)
    return events
