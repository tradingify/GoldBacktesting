"""
Optimal Trade Entry (OTE) Detector — research adapter.

ICT concept: after a directional leg (swing H → swing L or vice versa),
the OTE zone is the 62 %–79 % Fibonacci retracement of that leg.

  Bullish OTE (for longs):
    After a SH → SL drop, price retraces upward.
    OTE = SL + (SH - SL) * [0.62 … 0.79]

  Bearish OTE (for shorts):
    After a SL → SH rally, price retraces downward.
    OTE = SH - (SH - SL) * [0.62 … 0.79]

Anti-lookahead guarantee
------------------------
A directional leg is formed by a Swing A and a consecutive Swing B.
The leg is confirmed on the confirmation bar of Swing B (index B + swing_length).
Scanning for OTE entry happens strictly *after* leg confirmation.
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

OTE_LOW  = 0.62
OTE_HIGH = 0.79

def _find_swings(highs: np.ndarray, lows: np.ndarray, length: int):
    sh, sl = [], []
    n = len(highs)
    for i in range(length, n - length):
        if (highs[i] == highs[i - length : i + length + 1].max()
                and highs[i] > highs[i - 1]
                and highs[i] > highs[i + 1]):
            sh.append(i)
        if (lows[i] == lows[i - length : i + length + 1].min()
                and lows[i] < lows[i - 1]
                and lows[i] < lows[i + 1]):
            sl.append(i)
    return sh, sl


def detect_ote(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    swing_length: int = 10,
) -> List[IndicatorEvent]:
    """
    Detect OTE zones and mitigation.

    Parameters
    ----------
    df : pd.DataFrame
    symbol : str
    timeframe : str
    swing_length : int

    Returns
    -------
    List[IndicatorEvent]
        OTE_ACTIVE, OTE_MITIGATED, OTE_EXPIRED events.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    times  = df.index
    n      = len(df)

    sh_bars, sl_bars = _find_swings(highs, lows, swing_length)

    # Build chronological event list of swings
    swing_events = sorted(
        [(b, "H", float(highs[b])) for b in sh_bars] +
        [(b, "L", float(lows[b]))  for b in sl_bars],
        key=lambda x: x[0],
    )

    events: List[IndicatorEvent] = []

    for k in range(len(swing_events) - 1):
        b_a, t_a, l_a = swing_events[k]
        b_b, t_b, l_b = swing_events[k + 1]

        leg_conf_idx = b_b + swing_length
        if leg_conf_idx >= n:
            continue
            
        conf_time = times[leg_conf_idx]

        if t_a == "H" and t_b == "L":
            # Bearish leg down (SH -> SL) -> Sets up a bearish retracement short setup (Bearish OTE)
            # Wait, retracing UP into premium means we want to SHORT. 
            # So the setup is Bearish Direction.
            sh_lvl, sl_lvl = l_a, l_b
            move = sh_lvl - sl_lvl
            if move <= 0:
                continue
                
            dir_val = Direction.BEARISH
            hi_ote  = sh_lvl - move * OTE_LOW   # Premium level (closer to SH)
            lo_ote  = sh_lvl - move * OTE_HIGH  # Discount level
            
            events.append(IndicatorEvent(
                timestamp=conf_time,
                symbol=symbol,
                timeframe=timeframe,
                direction=dir_val,
                event_type=EventType.OTE_ACTIVE,
                level_or_zone=(lo_ote, hi_ote),
                state=EventState.ACTIVE,
                metadata={"anchor_origin": sh_lvl, "anchor_target": sl_lvl},
                score_contribution=0
            ))

            mitigated = False
            for j in range(leg_conf_idx + 1, n):
                if not mitigated and highs[j] >= lo_ote:
                    mitigated = True
                    events.append(IndicatorEvent(
                        timestamp=times[j],
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=dir_val,
                        event_type=EventType.OTE_MITIGATED,
                        level_or_zone=(lo_ote, hi_ote),
                        state=EventState.MITIGATED,
                        metadata={"anchor_origin": sh_lvl},
                        score_contribution=compute_score(EventType.OTE_MITIGATED, timeframe)
                    ))
                
                # Invalidation: price breaks the origin swing high
                if closes[j] > sh_lvl:
                    events.append(IndicatorEvent(
                        timestamp=times[j],
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=dir_val,
                        event_type=EventType.OTE_EXPIRED,
                        level_or_zone=(lo_ote, hi_ote),
                        state=EventState.EXPIRED,
                        metadata={"anchor_origin": sh_lvl},
                        score_contribution=0
                    ))
                    break

        elif t_a == "L" and t_b == "H":
            # Bullish leg up (SL -> SH) -> Sets up a bullish retracement long setup (Bullish OTE)
            sl_lvl, sh_lvl = l_a, l_b
            move = sh_lvl - sl_lvl
            if move <= 0:
                continue
                
            dir_val = Direction.BULLISH
            hi_ote  = sl_lvl + move * OTE_HIGH # Premium level
            lo_ote  = sl_lvl + move * OTE_LOW  # Discount level
            
            events.append(IndicatorEvent(
                timestamp=conf_time,
                symbol=symbol,
                timeframe=timeframe,
                direction=dir_val,
                event_type=EventType.OTE_ACTIVE,
                level_or_zone=(lo_ote, hi_ote),
                state=EventState.ACTIVE,
                metadata={"anchor_origin": sl_lvl, "anchor_target": sh_lvl},
                score_contribution=0
            ))

            mitigated = False
            for j in range(leg_conf_idx + 1, n):
                if not mitigated and lows[j] <= hi_ote:
                    mitigated = True
                    events.append(IndicatorEvent(
                        timestamp=times[j],
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=dir_val,
                        event_type=EventType.OTE_MITIGATED,
                        level_or_zone=(lo_ote, hi_ote),
                        state=EventState.MITIGATED,
                        metadata={"anchor_origin": sl_lvl},
                        score_contribution=compute_score(EventType.OTE_MITIGATED, timeframe)
                    ))
                
                # Invalidation: price breaks the origin swing low
                if closes[j] < sl_lvl:
                    events.append(IndicatorEvent(
                        timestamp=times[j],
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=dir_val,
                        event_type=EventType.OTE_EXPIRED,
                        level_or_zone=(lo_ote, hi_ote),
                        state=EventState.EXPIRED,
                        metadata={"anchor_origin": sl_lvl},
                        score_contribution=0
                    ))
                    break

    events.sort(key=lambda e: e.timestamp)
    return events
