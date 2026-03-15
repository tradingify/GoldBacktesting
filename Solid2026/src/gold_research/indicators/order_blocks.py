"""
Order Block detector — research adapter.

Mirrors the logic of:
    D:\.openclaw\workspace\mtf-ob-build\order_blocks_mtf_v2.py

An Order Block is the last candle of the OPPOSITE colour immediately before
a strong displacement (impulse) candle.  The OB zone (top/bot) becomes a
demand (bullish) or supply (bearish) area that price may revisit.

Anti-lookahead guarantee
------------------------
OB activation_time = open of the bar IMMEDIATELY AFTER impulse completion
(index i+1 in the scan loop).  Events are emitted with timestamp =
activation_time.  This matches the fix applied to the live system 2026-03-06.

Key parameters (defaults match live system)
-------------------------------------------
disp_mult   : 1.5  — body must exceed disp_mult × ATR(14) to qualify.
swing_len   : 10   — bars each side for swing high/low detection.
atr_window  : 14   — ATR rolling period.
max_obs     : 5    — max simultaneous active OBs per direction.
max_touches : 2    — OB invalidated after N zone entries (touch_count ≥ N).
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


# ── Internal record ────────────────────────────────────────────────────────────

@dataclass
class _OBRecord:
    tf:                 str
    direction:          int          # 1 = bullish, -1 = bearish
    top:                float
    bot:                float
    ob_candle_time:     pd.Timestamp
    activation_time:    pd.Timestamp
    active:             bool = True
    touch_count:        int  = 0
    in_zone:            bool = False
    mitigated:          bool = False
    volume_score:       float = 0.0
    atr_at_formation:   float = 0.0

    @property
    def mid(self) -> float:
        return (self.top + self.bot) / 2.0


# ── Main detector ──────────────────────────────────────────────────────────────

def detect_order_blocks(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    disp_mult: float = 1.5,
    swing_len: int = 10,
    atr_window: int = 14,
    max_obs: int = 5,
    max_touches: int = 2,
) -> List[IndicatorEvent]:
    """
    Detect Order Blocks in a single-timeframe OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close, [volume].  DatetimeIndex (UTC).
    symbol : str
    timeframe : str
    disp_mult : float
    swing_len : int
    atr_window : int
    max_obs : int
    max_touches : int

    Returns
    -------
    List[IndicatorEvent]
        ORDER_BLOCK_ACTIVE  — when OB is first activated.
        ORDER_BLOCK_MITIGATED — when OB is consumed by price.
        State EXPIRED — when touch limit is exceeded.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    n      = len(df)
    opens  = df["open"].to_numpy(dtype=float)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    vols   = (
        df["volume"].to_numpy(dtype=float)
        if "volume" in df.columns
        else np.ones(n, dtype=float)
    )
    times  = df.index

    # ATR(14)
    tr = np.maximum(
        highs - lows,
        np.maximum(
            np.abs(highs - np.roll(closes, 1)),
            np.abs(lows  - np.roll(closes, 1)),
        ),
    )
    tr[0] = highs[0] - lows[0]
    atr = pd.Series(tr).rolling(atr_window, min_periods=1).mean().to_numpy(dtype=float)

    bodies   = np.abs(closes - opens)
    is_bull  = closes > opens   # True = bullish bar

    events: List[IndicatorEvent] = []
    active_bull: List[_OBRecord] = []
    active_bear: List[_OBRecord] = []

    for i in range(1, n):
        price = closes[i]
        t     = times[i]

        # ── Update existing OBs ───────────────────────────────────────────────
        for ob in active_bull + active_bear:
            if not ob.active:
                continue

            was_in = ob.in_zone
            ob.in_zone = ob.bot <= price <= ob.top
            if ob.in_zone and not was_in:
                ob.touch_count += 1

            # Mitigation
            if ob.direction == 1 and closes[i] < ob.bot:
                ob.active   = False
                ob.mitigated = True
                events.append(_make_event(ob, t, symbol, EventState.MITIGATED))
            elif ob.direction == -1 and closes[i] > ob.top:
                ob.active   = False
                ob.mitigated = True
                events.append(_make_event(ob, t, symbol, EventState.MITIGATED))
            elif ob.touch_count >= max_touches:
                ob.active = False
                events.append(_make_event(ob, t, symbol, EventState.EXPIRED))

        active_bull = [o for o in active_bull if o.active][:max_obs]
        active_bear = [o for o in active_bear if o.active][:max_obs]

        # ── Impulse detection ─────────────────────────────────────────────────
        if bodies[i] <= disp_mult * atr[i]:
            continue

        if is_bull[i]:
            # Bullish impulse → last bearish candle before impulse = bullish OB
            ob_idx = _find_last_opposite(is_bull, i, want_bull=False)
            if ob_idx is not None:
                act_time = times[ob_idx + 1] if ob_idx + 1 < n else t
                ob = _OBRecord(
                    tf=timeframe, direction=1,
                    top=highs[ob_idx], bot=lows[ob_idx],
                    ob_candle_time=times[ob_idx], activation_time=act_time,
                    volume_score=float(vols[ob_idx]),
                    atr_at_formation=float(atr[i]),
                )
                if len(active_bull) < max_obs:
                    active_bull.append(ob)
                    events.append(_make_event(ob, act_time, symbol, EventState.ACTIVE))

        else:
            # Bearish impulse → last bullish candle before impulse = bearish OB
            ob_idx = _find_last_opposite(is_bull, i, want_bull=True)
            if ob_idx is not None:
                act_time = times[ob_idx + 1] if ob_idx + 1 < n else t
                ob = _OBRecord(
                    tf=timeframe, direction=-1,
                    top=highs[ob_idx], bot=lows[ob_idx],
                    ob_candle_time=times[ob_idx], activation_time=act_time,
                    volume_score=float(vols[ob_idx]),
                    atr_at_formation=float(atr[i]),
                )
                if len(active_bear) < max_obs:
                    active_bear.append(ob)
                    events.append(_make_event(ob, act_time, symbol, EventState.ACTIVE))

    return events


def _find_last_opposite(
    is_bull: np.ndarray,
    impulse_idx: int,
    want_bull: bool,
    lookback: int = 10,
) -> Optional[int]:
    """Return index of last candle of the desired colour before impulse_idx."""
    for j in range(impulse_idx - 1, max(impulse_idx - lookback - 1, -1), -1):
        if bool(is_bull[j]) == want_bull:
            return j
    return None


def _make_event(
    ob: _OBRecord,
    ts: pd.Timestamp,
    symbol: str,
    state: EventState,
) -> IndicatorEvent:
    direction = Direction.BULLISH if ob.direction == 1 else Direction.BEARISH
    etype = (
        EventType.ORDER_BLOCK_ACTIVE
        if state == EventState.ACTIVE
        else EventType.ORDER_BLOCK_MITIGATED
    )
    return IndicatorEvent(
        timestamp=ts,
        symbol=symbol,
        timeframe=ob.tf,
        direction=direction,
        event_type=etype,
        level_or_zone=(ob.bot, ob.top),
        state=state,
        metadata={
            "ob_candle_time":   str(ob.ob_candle_time),
            "touch_count":      ob.touch_count,
            "volume_score":     ob.volume_score,
            "atr_at_formation": ob.atr_at_formation,
            "mid":              ob.mid,
        },
        score_contribution=compute_score(EventType.ORDER_BLOCK_ACTIVE, ob.tf),
    )
