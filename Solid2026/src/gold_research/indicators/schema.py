"""
Unified event schema for the ICT indicator layer.

Every indicator adapter in gold_research.indicators.* emits IndicatorEvent
objects using the types defined here.  This is the single contract between:
  - Indicator adapters  (produce events)
  - EventRegistry       (tracks active events)
  - BarProcessor        (labels bars with confluence)
  - ICT strategies      (consume ConfluenceResult)

Anti-lookahead contract
-----------------------
event.timestamp MUST equal the close time of the CONFIRMING bar.

See LOOKAHEAD_RULES below for per-concept rules derived from auditing the
K live codebase (confluence_scorer.py, order_blocks_mtf_v2.py, etc.).

Score matrix
------------
Derived from K's live confluence_scorer.py (MIN_FIRE_SCORE = 6 as of 2026-03-12).
Higher-timeframe OBs score +2; M15/M5 OBs score +1.
Structure events score +2 (BOS on M5/M15) or +1 (CHoCH / higher TFs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd


# ── Enums ──────────────────────────────────────────────────────────────────────

class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class EventType(str, Enum):
    # Order Blocks
    ORDER_BLOCK_FORMED    = "order_block_formed"
    ORDER_BLOCK_ACTIVE    = "order_block_active"
    ORDER_BLOCK_MITIGATED = "order_block_mitigated"

    # Market Structure
    BOS   = "bos"
    CHOCH = "choch"

    # Fair Value Gaps
    FVG_FORMED    = "fvg_formed"
    FVG_ACTIVE    = "fvg_active"
    FVG_MITIGATED = "fvg_mitigated"

    # Liquidity Pools
    LIQUIDITY_POOL_FORMED = "liquidity_pool_formed"
    LIQUIDITY_POOL_SWEPT  = "liquidity_pool_swept"

    # Optimal Trade Entry (Fibonacci OTE)
    OTE_ACTIVE  = "ote_active"
    OTE_ENTERED = "ote_entered"

    # Previous Period Levels
    PREV_HIGH_FORMED = "prev_high_formed"
    PREV_LOW_FORMED  = "prev_low_formed"
    PREV_HIGH_BROKEN = "prev_high_broken"
    PREV_LOW_BROKEN  = "prev_low_broken"

    # Session
    SESSION_OPEN       = "session_open"
    SESSION_CLOSE      = "session_close"
    SESSION_RANGE_HIGH = "session_range_high"
    SESSION_RANGE_LOW  = "session_range_low"
    SESSION_SWEEP      = "session_sweep"

    # Engulfing candles
    ENGULFING = "engulfing"

    # Breaker Blocks
    BREAKER_BLOCK_FORMED   = "breaker_block_formed"
    BREAKER_BLOCK_RETESTED = "breaker_block_retested"
    BREAKER_BLOCK_BROKEN   = "breaker_block_broken"


class EventState(str, Enum):
    PENDING   = "pending"     # Formed; activation bar not yet reached
    ACTIVE    = "active"      # Live; price not yet in zone
    IN_ZONE   = "in_zone"     # Price currently inside zone / at level
    MITIGATED = "mitigated"   # Zone consumed; event closed
    EXPIRED   = "expired"     # Invalidated by structure or touch limit


# ── Core types ────────────────────────────────────────────────────────────────

# Single price level OR a (low, high) zone tuple
LevelOrZone = Union[float, Tuple[float, float]]


@dataclass
class IndicatorEvent:
    """
    Canonical output unit from every indicator adapter.

    Fields
    ------
    timestamp        : UTC bar-close of the CONFIRMING bar (anti-lookahead boundary).
    symbol           : Instrument, e.g. "XAUUSD".
    timeframe        : Source timeframe, e.g. "M5", "M15", "H1".
    direction        : Directional bias of this event.
    event_type       : What concept/event this is.
    level_or_zone    : Float (single level) or (lo, hi) tuple (zone).
    state            : Lifecycle state at time of emission.
    metadata         : Freeform dict for indicator-specific extra fields.
    score_contribution: Pre-computed confluence score (from SCORE_MATRIX).
    """
    timestamp:         pd.Timestamp
    symbol:            str
    timeframe:         str
    direction:         Direction
    event_type:        EventType
    level_or_zone:     LevelOrZone
    state:             EventState
    metadata:          Dict[str, Any] = field(default_factory=dict)
    score_contribution: int = 0

    # Unique key for registry deduplication.  Subclasses / factories may override.
    def event_key(self) -> str:
        if isinstance(self.level_or_zone, tuple):
            lo, hi = self.level_or_zone
            lvl = f"{lo:.2f}-{hi:.2f}"
        else:
            lvl = f"{self.level_or_zone:.2f}"
        return f"{self.event_type.value}|{self.timeframe}|{self.direction.value}|{lvl}"

    def is_zone(self) -> bool:
        return isinstance(self.level_or_zone, tuple)

    def price_in_zone(self, price: float, tolerance: float = 0.0) -> bool:
        """True if price touches or is inside this event's level/zone."""
        if isinstance(self.level_or_zone, tuple):
            lo, hi = self.level_or_zone
            return (lo - tolerance) <= price <= (hi + tolerance)
        return abs(price - float(self.level_or_zone)) <= tolerance

    def zone_midpoint(self) -> float:
        if isinstance(self.level_or_zone, tuple):
            lo, hi = self.level_or_zone
            return (lo + hi) / 2.0
        return float(self.level_or_zone)

    def __repr__(self) -> str:
        return (
            f"IndicatorEvent({self.event_type.value} {self.direction.value} "
            f"{self.timeframe} @ {self.timestamp:%Y-%m-%d %H:%M} "
            f"state={self.state.value} score={self.score_contribution})"
        )


# ── Score matrix ───────────────────────────────────────────────────────────────
# (event_type, timeframe) → score contribution.
# Derived from K's live confluence_scorer.py (as of 2026-03-12).
# MIN_FIRE_SCORE = 6 for a trade signal.

SCORE_MATRIX: Dict[EventType, Dict[str, int]] = {
    EventType.ORDER_BLOCK_ACTIVE: {
        "D1": 2, "H4": 2, "H1": 2, "M30": 2, "M15": 1, "M5": 1,
    },
    EventType.BOS: {
        "M5": 2, "M15": 2, "M30": 1, "H1": 1, "H4": 1, "D1": 1,
    },
    EventType.CHOCH: {
        "M5": 1, "M15": 1, "M30": 1, "H1": 1, "H4": 1, "D1": 1,
    },
    EventType.ENGULFING: {
        "M5": 2, "M15": 2, "M30": 2, "H1": 1, "H4": 0, "D1": 0,
    },
    EventType.FVG_ACTIVE: {
        "M5": 1, "M15": 1, "M30": 1, "H1": 1, "H4": 1, "D1": 1,
    },
    EventType.OTE_ENTERED: {
        "M5": 1, "M15": 1, "H1": 1, "H4": 1,
    },
    EventType.BREAKER_BLOCK_FORMED: {
        "M5": 1, "M15": 1, "M30": 1, "H1": 1,
    },
    EventType.BREAKER_BLOCK_RETESTED: {
        "M5": 2, "M15": 2, "M30": 1, "H1": 1,
    },
    EventType.SESSION_SWEEP: {
        "M5": 2, "M15": 2, "M30": 1,
    },
    EventType.LIQUIDITY_POOL_SWEPT: {
        "M5": 1, "M15": 1, "M30": 1, "H1": 1, "H4": 1, "15m": 1, "1h": 1, "4h": 1, "1d": 1, "1m": 1, "5m": 1, "30m": 1
    },
    EventType.PREV_HIGH_BROKEN: {
        "D1": 1, "H4": 1, "H1": 1,
    },
    EventType.PREV_LOW_BROKEN: {
        "D1": 1, "H4": 1, "H1": 1,
    },
}

MIN_FIRE_SCORE: int = 6


def compute_score(event_type: EventType, timeframe: str) -> int:
    """Look up score contribution.  Returns 0 for unlisted event/TF pairs."""
    # Normalize timeframe string to handle "15m" -> "M15" and "1h" -> "H1"
    tf = timeframe.upper().replace("MINS", "M").replace("MIN", "M").replace("HOURS", "H").replace("HOUR", "H")
    if tf.endswith("M") and tf[0].isdigit():
        tf = "M" + tf[:-1]
    elif tf.endswith("T") and tf[0].isdigit(): # Nautilus uses T for minutes sometimes
        tf = "M" + tf[:-1]
    elif tf.endswith("H") and tf[0].isdigit():
        tf = "H" + tf[:-1]
    elif tf.endswith("D") and tf[0].isdigit():
        tf = "D" + tf[:-1]
        
    score = SCORE_MATRIX.get(event_type, {}).get(tf, 0)
    if score == 0:
        # Try raw just in case
        score = SCORE_MATRIX.get(event_type, {}).get(timeframe, 0)
        
    # Temporary debug for first few calls
    if not hasattr(compute_score, "count"): compute_score.count = 0
    if compute_score.count < 10:
        print(f"[DEBUG] compute_score: type={event_type.value} tf_raw={timeframe} tf_norm={tf} -> score={score}")
        compute_score.count += 1
        
    return score


# ── Confluence result ──────────────────────────────────────────────────────────

@dataclass
class ConfluenceResult:
    """Aggregated confluence output for a single base-TF bar."""
    timestamp:     pd.Timestamp
    symbol:        str
    timeframe:     str           # Base TF being assessed (usually M15 or M5)
    total_score:   int = 0
    bull_score:    int = 0
    bear_score:    int = 0
    direction:     Direction = Direction.NEUTRAL
    fire:          bool = False
    active_events: List[IndicatorEvent] = field(default_factory=list)
    combo:         str = ""
    metadata:      Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_events(
        cls,
        ts: pd.Timestamp,
        symbol: str,
        base_tf: str,
        events: List[IndicatorEvent],
    ) -> "ConfluenceResult":
        """Build a ConfluenceResult from a list of currently active events."""
        if not events:
            return cls(
                timestamp=ts, symbol=symbol, timeframe=base_tf,
                total_score=0, direction=Direction.NEUTRAL,
                fire=False, active_events=[], combo="",
            )

        bull_score = sum(
            e.score_contribution for e in events if e.direction == Direction.BULLISH
        )
        bear_score = sum(
            e.score_contribution for e in events if e.direction == Direction.BEARISH
        )

        if bull_score >= bear_score:
            direction = Direction.BULLISH
            total_score = bull_score
            directional_events = [e for e in events if e.direction == Direction.BULLISH]
        else:
            direction = Direction.BEARISH
            total_score = bear_score
            directional_events = [e for e in events if e.direction == Direction.BEARISH]

        combo_parts = sorted({e.event_type.value.replace("_", " ").title() for e in directional_events})
        combo = "+".join(combo_parts)

        return cls(
            timestamp=ts,
            symbol=symbol,
            timeframe=base_tf,
            total_score=total_score,
            bull_score=bull_score,
            bear_score=bear_score,
            direction=direction,
            fire=total_score >= MIN_FIRE_SCORE,
            active_events=directional_events,
            combo=combo,
        )


# ── Anti-lookahead rules (documentation) ──────────────────────────────────────

LOOKAHEAD_RULES: Dict[str, str] = {
    "ORDER_BLOCK": (
        "OB activation_time = open of bar AFTER impulse completes (index i+1). "
        "Events emitted with timestamp = activation_time.  "
        "Fixed in live system 2026-03-06; matches here."
    ),
    "MARKET_STRUCTURE": (
        "Fractals require `length` confirmed bars on EACH side.  "
        "Pivot at index p is only visible at bar p + length.  "
        "BOS/CHoCH event timestamp = close of the breaking bar."
    ),
    "FVG": (
        "3-candle pattern: gap between bar[i-1].high and bar[i+1].low.  "
        "FVG is formed at bar i+1 close (earliest the full gap is known).  "
        "Mitigation scan starts at bar i+2."
    ),
    "LIQUIDITY_POOL": (
        "Swing pivots require swing_length bars each side.  "
        "Pool confirmed at bar p + swing_length.  "
        "Sweep check: close breaches level after pool confirmation."
    ),
    "OTE": (
        "Leg detection requires completed pivot on each side.  "
        "InOTE flag set when current bar CLOSE enters 62–79% zone; "
        "no future bar data used."
    ),
    "PREV_HIGH_LOW": (
        "Previous period H/L uses only completed periods.  "
        "D1 H/L available from start of next day.  "
        "W1 H/L available from Monday open of next week.  "
        "No intra-period lookahead."
    ),
    "ENGULFING": (
        "Pattern uses bar[i] vs bar[i-1] only.  "
        "Event timestamp = close of bar[i].  "
        "No future bar data used."
    ),
    "BREAKER_BLOCK": (
        "Breaker is a previously mitigated OB.  "
        "Cannot form before OB mitigation is confirmed.  "
        "Retest and break scans are forward-only from breaker formation time."
    ),
    "SESSION_SWEEP": (
        "Range marks the CLOSE of each range-window bar.  "
        "Sweep fires when bar CLOSE is back inside range after wick breach.  "
        "No intra-bar fill assumptions."
    ),
}
