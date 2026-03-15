"""
Session Sweeps Detector — research adapter.

ICT concept: Price often sweeps the high/low of a previous session
(e.g., London sweeping Tokyo's high) to grab liquidity before reversing.
"""

from __future__ import annotations

import datetime
from typing import List, Dict

import numpy as np
import pandas as pd

from src.gold_research.indicators.schema import (
    Direction,
    EventState,
    EventType,
    IndicatorEvent,
    compute_score,
)
from src.gold_research.indicators.sessions_model import SessionModel


def detect_session_sweeps(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15"
) -> List[IndicatorEvent]:
    """
    Detect session highs/lows and subsequent liquidity sweeps.

    Parameters
    ----------
    df : pd.DataFrame
    symbol : str
    timeframe : str

    Returns
    -------
    List[IndicatorEvent]
        SESSION_SWEPT events.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    times  = df.index
    
    model = SessionModel()
    
    # State tracking
    # Dictionary mapping session_name -> current active state
    tracking: Dict[str, Dict] = {}
    
    events: List[IndicatorEvent] = []

    for j, dt in enumerate(times):
        dt_pd = pd.to_datetime(dt)
        # Assuming dt is close time, maybe need to check session using bar time
        active_sessions = model.get_active_sessions(dt_pd)
        
        # 1. Update active sessions (build their high/low)
        for s_name in active_sessions:
            if s_name not in tracking or tracking[s_name]["status"] == "closed":
                tracking[s_name] = {
                    "status": "active",
                    "high": highs[j],
                    "low": lows[j],
                    "swept_high": False,
                    "swept_low": False,
                }
            else:
                tracking[s_name]["high"] = max(tracking[s_name]["high"], highs[j])
                tracking[s_name]["low"] = min(tracking[s_name]["low"], lows[j])
                
        # 2. Transition sessions from active to closed if they are no longer active
        for s_name, state in tracking.items():
            if state["status"] == "active" and s_name not in active_sessions:
                state["status"] = "closed"
                # Now it becomes a target for sweeping
                
        # 3. Check for sweeps of closed sessions
        for s_name, state in tracking.items():
            if state["status"] == "closed":
                sweep_res = SessionModel.detect_sweep(
                    current_high=highs[j],
                    current_low=lows[j],
                    current_close=closes[j],
                    target_high=state["high"],
                    target_low=state["low"]
                )
                
                if sweep_res in ("bearish", "both") and not state["swept_high"]:
                    state["swept_high"] = True
                    events.append(IndicatorEvent(
                        timestamp=times[j],
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=Direction.BEARISH,
                        event_type=EventType.SESSION_SWEPT,
                        level_or_zone=state["high"],
                        state=EventState.MITIGATED,
                        metadata={"target_session": s_name, "sweep_type": "HIGH"},
                        score_contribution=compute_score(EventType.SESSION_SWEPT, timeframe)
                    ))
                    
                if sweep_res in ("bullish", "both") and not state["swept_low"]:
                    state["swept_low"] = True
                    events.append(IndicatorEvent(
                        timestamp=times[j],
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=Direction.BULLISH,
                        event_type=EventType.SESSION_SWEPT,
                        level_or_zone=state["low"],
                        state=EventState.MITIGATED,
                        metadata={"target_session": s_name, "sweep_type": "LOW"},
                        score_contribution=compute_score(EventType.SESSION_SWEPT, timeframe)
                    ))

    return events
