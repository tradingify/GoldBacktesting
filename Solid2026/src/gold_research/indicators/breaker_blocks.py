"""
Breaker Blocks Detector — research adapter.

ICT concept: when an Order Block is "mitigated" (price trades through it),
the OB flips polarity and becomes a Breaker Block — a supply/resistance
zone that price is expected to respect from the *opposite* side.

  Bullish OB mitigated (close below bot) → Bearish Breaker (now supply)
  Bearish OB mitigated (close above top) → Bullish Breaker (now demand)

Anti-lookahead guarantee
------------------------
A breaker cannot form before the underlying OB's mitigation is confirmed.
Retest and break scans are forward-only from the breaker formation time.
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
from src.gold_research.indicators.order_blocks import detect_order_blocks


def detect_breakers(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    **ob_kwargs
) -> List[IndicatorEvent]:
    """
    Detect Breaker Blocks from mitigated Order Blocks.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close, volume. DatetimeIndex.
    symbol : str
    timeframe : str
    **ob_kwargs : dict
        Parameters passed to detect_order_blocks (e.g., swing_len, disp_mult).

    Returns
    -------
    List[IndicatorEvent]
        BREAKER_BLOCK_FORMED, BREAKER_BLOCK_RETESTED events.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    n      = len(df)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    times  = df.index
    
    # 1. Get raw robust Order Blocks
    ob_events = detect_order_blocks(df, symbol=symbol, timeframe=timeframe, **ob_kwargs)
    
    events: List[IndicatorEvent] = []
    active_breakers = []

    # 2. Extract mitigated OBs to form Breakers
    for event in ob_events:
        if event.state == EventState.MITIGATED and event.event_type == EventType.ORDER_BLOCK_MITIGATED:
            # Polarity completely flips
            breaker_dir = Direction.BEARISH if event.direction == Direction.BULLISH else Direction.BULLISH
            bot, top = event.level_or_zone
            
            formed_event = IndicatorEvent(
                timestamp=event.timestamp,
                symbol=symbol,
                timeframe=timeframe,
                direction=breaker_dir,
                event_type=EventType.BREAKER_BLOCK_FORMED,
                level_or_zone=(bot, top),
                state=EventState.ACTIVE,
                metadata={
                    "original_ob_dir": event.direction.value,
                    "volume_score": event.metadata.get("volume_score", 0.0),
                },
                score_contribution=compute_score(EventType.BREAKER_BLOCK_FORMED, timeframe)
            )
            events.append(formed_event)
            active_breakers.append({
                "direction": breaker_dir,
                "top": top,
                "bot": bot,
                "formed_time": event.timestamp,
                "retested": False,
                "volume_score": event.metadata.get("volume_score", 0.0)
            })

    if not active_breakers:
        return events

    # 3. Fast forward-scan for retests and breaks using grouped array operations where possible
    for brk in active_breakers:
        try:
            start_idx = times.get_loc(brk["formed_time"])
        except KeyError:
            continue
            
        if start_idx + 1 >= n:
            continue
            
        top, bot = brk["top"], brk["bot"]
        b_dir = brk["direction"]
        
        for j in range(int(start_idx) + 1, n):
            # Retest check (must touch the zone)
            if not brk["retested"]:
                if lows[j] <= top and highs[j] >= bot:
                    brk["retested"] = True
                    events.append(IndicatorEvent(
                        timestamp=times[j],
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=b_dir,
                        event_type=EventType.BREAKER_BLOCK_RETESTED,
                        level_or_zone=(bot, top),
                        state=EventState.MITIGATED, # Treated as hit
                        metadata={"volume_score": brk["volume_score"]},
                        score_contribution=compute_score(EventType.BREAKER_BLOCK_RETESTED, timeframe)
                    ))
            
            # Broken check
            is_broken = False
            if b_dir == Direction.BULLISH and closes[j] < bot:
                is_broken = True
            elif b_dir == Direction.BEARISH and closes[j] > top:
                is_broken = True
                
            if is_broken:
                events.append(IndicatorEvent(
                    timestamp=times[j],
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=b_dir,
                    event_type=EventType.BREAKER_BLOCK_BROKEN,
                    level_or_zone=(bot, top),
                    state=EventState.EXPIRED,
                    metadata={"volume_score": brk["volume_score"]},
                    score_contribution=0
                ))
                break # Stop tracking this breaker once structurally broken
                
    # Ensure chronological order
    events.sort(key=lambda e: e.timestamp)
    return events
