#!/usr/bin/env python3
"""
Indicator Research Matrix — Solid2026
======================================
Tests each of K's ICT indicators individually, then in combinations, using a
simple vectorized forward-scan backtest over the full XAUUSD price history
in D:\\.openclaw\\GoldBacktesting\\bars\\.

Philosophy: each test is one simple, explicit rule.  No magic, no lookahead.

Run
---
    $env:PYTHONPATH="D:\\.openclaw\\GoldBacktesting\\Solid2026"
    python scripts\\run_indicator_research.py

Output
------
    results/raw_runs/INDICATOR_RESEARCH/
        leaderboard.csv                     ← all experiments ranked by Sharpe
        <experiment>_trades.csv             ← per-trade detail
        indicator_research_report.html      ← full HTML summary

Falsification gates (all must pass for PASS verdict)
-------------------------------------------------------
    trades   >= 20
    Sharpe   >= 0.5
    PF       >= 1.0
    Max DD   >= -20 R  (i.e. never lose more than 20R peak-to-trough)
    Win Rate >= 35 %
"""

from __future__ import annotations

import sys
import math
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any, Callable, Tuple

import numpy as np
import pandas as pd

# ── Project root ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(r"D:\.openclaw\GoldBacktesting\Solid2026")
BARS_DIR     = Path(r"D:\.openclaw\GoldBacktesting\bars")
RESULTS_DIR  = PROJECT_ROOT / "results" / "raw_runs" / "INDICATOR_RESEARCH"

sys.path.insert(0, str(PROJECT_ROOT))

from gold_research.indicators.order_blocks     import detect_order_blocks
from gold_research.indicators.market_structure import detect_market_structure
from gold_research.indicators.fvg              import detect_fvg
from gold_research.indicators.session_sweep    import detect_session_sweep
from gold_research.indicators.engulfing        import detect_engulfing
from gold_research.indicators.liquidity_pools  import detect_liquidity_pools
from gold_research.indicators.ote              import detect_ote
from gold_research.indicators.prev_high_low    import detect_prev_high_low
from gold_research.indicators.breaker_blocks   import detect_breaker_blocks
from gold_research.indicators.schema           import (
    EventType, Direction, EventState, IndicatorEvent,
)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

RR          = 2.0      # Reward : risk ratio for all tests
SL_BUFFER   = 0.001    # 0.1 % beyond zone edge for SL
MAX_HOLD    = 200      # Max bars in trade before timeout exit
COMBO_WIN   = 8        # Window (bars) for two-indicator confluence check

GATES = dict(min_trades=20, min_sharpe=0.5, min_pf=1.0,
             max_mdd_r=-20.0, min_wr=35.0)

TF_FILES: Dict[str, str] = {
    "M5":  "xauusd_5_mins.parquet",
    "M15": "xauusd_15_mins.parquet",
    "M30": "xauusd_30_mins.parquet",
    "H1":  "xauusd_1_hour.parquet",
    "H4":  "xauusd_4_hours.parquet",
    "D1":  "xauusd_1_day.parquet",
}

_df_cache: Dict[str, pd.DataFrame] = {}


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_bars(tf: str) -> pd.DataFrame:
    if tf in _df_cache:
        return _df_cache[tf]
    path = BARS_DIR / TF_FILES[tf]
    df = pd.read_parquet(path)
    df.columns = [c.lower() for c in df.columns]
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    if "volume" in df.columns:
        df["volume"] = df["volume"].apply(
            lambda v: max(0, int(v)) if pd.notna(v) else 0
        )
    _df_cache[tf] = df
    print(f"  Loaded {tf}: {len(df):,} bars  "
          f"{df.index[0].date()} → {df.index[-1].date()}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# TRADE DATACLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Trade:
    entry_time:   str
    exit_time:    str
    direction:    str     # "long" | "short"
    entry_price:  float
    sl_price:     float
    tp_price:     float
    exit_price:   float
    outcome:      str     # "win" | "loss" | "timeout"
    r_multiple:   float


# ══════════════════════════════════════════════════════════════════════════════
# VECTORIZED BACKTESTER
# ══════════════════════════════════════════════════════════════════════════════

def run_backtest(
    df: pd.DataFrame,
    signals: List[Dict[str, Any]],
    rr: float = RR,
    max_hold: int = MAX_HOLD,
) -> List[Trade]:
    """
    Forward-scan backtest.

    Each signal dict must have:
        entry_idx   int
        entry_time  pd.Timestamp
        direction   "long" | "short"
        entry_price float
        sl_price    float
        tp_price    float
    """
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    times  = df.index
    n      = len(df)

    trades: List[Trade] = []
    in_trade_until: int = -1   # bar index when prior trade exits

    for sig in signals:
        idx = int(sig["entry_idx"])
        if idx <= in_trade_until or idx >= n - 1:
            continue

        ep  = float(sig["entry_price"])
        sl  = float(sig["sl_price"])
        tp  = float(sig["tp_price"])
        drn = sig["direction"]

        risk = abs(ep - sl)
        if risk <= 0:
            continue

        # Sanity: SL must be on the right side of entry
        if drn == "long"  and sl >= ep:
            continue
        if drn == "short" and sl <= ep:
            continue

        outcome    = "timeout"
        exit_price = closes[min(idx + max_hold, n - 1)]
        exit_idx   = min(idx + max_hold, n - 1)

        for j in range(idx + 1, min(idx + max_hold + 1, n)):
            h, lo = highs[j], lows[j]
            if drn == "long":
                if lo <= sl and h >= tp:
                    outcome, exit_price, exit_idx = "loss", sl, j; break
                elif h >= tp:
                    outcome, exit_price, exit_idx = "win",  tp, j; break
                elif lo <= sl:
                    outcome, exit_price, exit_idx = "loss", sl, j; break
            else:  # short
                if h >= sl and lo <= tp:
                    outcome, exit_price, exit_idx = "loss", sl, j; break
                elif lo <= tp:
                    outcome, exit_price, exit_idx = "win",  tp, j; break
                elif h >= sl:
                    outcome, exit_price, exit_idx = "loss", sl, j; break

        if outcome == "win":
            r = rr
        elif outcome == "loss":
            r = -1.0
        else:
            r = ((exit_price - ep) / risk) if drn == "long" else ((ep - exit_price) / risk)

        trades.append(Trade(
            entry_time=str(sig["entry_time"]),
            exit_time=str(times[exit_idx]),
            direction=drn,
            entry_price=round(ep, 4),
            sl_price=round(sl, 4),
            tp_price=round(tp, 4),
            exit_price=round(exit_price, 4),
            outcome=outcome,
            r_multiple=round(r, 3),
        ))
        in_trade_until = exit_idx

    return trades


# ══════════════════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════════════════

def compute_metrics(trades: List[Trade], label: str, tf: str) -> Dict[str, Any]:
    n = len(trades)
    base = dict(experiment=label, timeframe=tf, trades=n,
                win_rate=0.0, avg_r=0.0, total_r=0.0,
                profit_factor=0.0, sharpe=0.0, max_dd_r=0.0,
                verdict="INSUFFICIENT_DATA",
                date_start="", date_end="")
    if n < 2:
        return base

    rs     = np.array([t.r_multiple for t in trades])
    wins   = rs[rs > 0]
    losses = rs[rs < 0]

    win_rate = float(len(wins) / n * 100)
    avg_r    = float(rs.mean())
    total_r  = float(rs.sum())
    pf       = float(wins.sum() / abs(losses.sum())) if len(losses) > 0 else 99.0

    # Trade-level Sharpe annualised by estimated trades/year
    if rs.std() > 0 and n >= 4:
        dur = (pd.Timestamp(trades[-1].entry_time) -
               pd.Timestamp(trades[0].entry_time)).days
        tpy = n / max(dur, 1) * 365
        sharpe = float(avg_r / rs.std() * math.sqrt(tpy))
    else:
        sharpe = 0.0

    # Max drawdown in R
    cumr    = np.cumsum(rs)
    run_max = np.maximum.accumulate(cumr)
    max_dd  = float((cumr - run_max).min())

    failing = []
    if n        < GATES["min_trades"]: failing.append(f"trades<{GATES['min_trades']}")
    if sharpe   < GATES["min_sharpe"]: failing.append(f"Sharpe<{GATES['min_sharpe']}")
    if pf       < GATES["min_pf"]:     failing.append(f"PF<{GATES['min_pf']}")
    if max_dd   < GATES["max_mdd_r"]:  failing.append(f"MDD>{abs(GATES['max_mdd_r'])}R")
    if win_rate < GATES["min_wr"]:     failing.append(f"WR<{GATES['min_wr']}%")

    verdict = "PASS" if not failing else "FAIL(" + ", ".join(failing) + ")"

    return dict(
        experiment=label, timeframe=tf, trades=n,
        win_rate=round(win_rate, 1),
        avg_r=round(avg_r, 3),
        total_r=round(total_r, 2),
        profit_factor=round(pf, 2),
        sharpe=round(sharpe, 2),
        max_dd_r=round(max_dd, 2),
        verdict=verdict,
        date_start=str(pd.Timestamp(trades[0].entry_time).date()),
        date_end=str(pd.Timestamp(trades[-1].entry_time).date()),
    )


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL GENERATORS  (one per indicator concept)
# ══════════════════════════════════════════════════════════════════════════════

def _ts_index(df: pd.DataFrame) -> Dict:
    """Fast timestamp → integer-index lookup."""
    return {t: i for i, t in enumerate(df.index)}


def signals_ob(events: List[IndicatorEvent], df: pd.DataFrame) -> List[Dict]:
    """
    Order Block zone-return entry.
    Rule: after OB activates, enter at first bar close that is inside the zone.
    SL  = OB.bot * (1 - buf)  [long]   or  OB.top * (1 + buf)  [short]
    TP  = entry + 2R  (or entry - 2R for short)
    """
    ts_idx  = _ts_index(df)
    highs   = df["high"].to_numpy(float)
    lows    = df["low"].to_numpy(float)
    closes  = df["close"].to_numpy(float)
    n       = len(df)
    signals = []
    seen    = set()

    for evt in events:
        if evt.event_type != EventType.ORDER_BLOCK_ACTIVE:
            continue
        key = evt.event_key()
        if key in seen:
            continue
        seen.add(key)

        act_idx = ts_idx.get(evt.timestamp, df.index.searchsorted(evt.timestamp))
        act_idx = min(act_idx, n - 1)

        ob_bot, ob_top = evt.level_or_zone
        drn = "long" if evt.direction == Direction.BULLISH else "short"

        for i in range(act_idx + 1, min(act_idx + 500, n)):
            if lows[i] <= ob_top and highs[i] >= ob_bot:
                ep = closes[i]
                if drn == "long":
                    sl   = ob_bot * (1 - SL_BUFFER)
                    risk = ep - sl
                    if risk <= 0:
                        continue
                    tp = ep + RR * risk
                else:
                    sl   = ob_top * (1 + SL_BUFFER)
                    risk = sl - ep
                    if risk <= 0:
                        continue
                    tp = ep - RR * risk
                signals.append(dict(entry_idx=i, entry_time=df.index[i],
                                    direction=drn, entry_price=ep,
                                    sl_price=sl, tp_price=tp))
                break

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_structure(events: List[IndicatorEvent], df: pd.DataFrame,
                      etype: EventType) -> List[Dict]:
    """
    CHoCH / BOS next-bar-open entry.
    Rule: on event bar close, enter next bar open.
    SL   = broken level  (now acts as support/resistance)
    TP   = 2R
    """
    ts_idx  = _ts_index(df)
    opens   = df["open"].to_numpy(float)
    n       = len(df)
    signals = []

    for evt in events:
        if evt.event_type != etype:
            continue
        bar = ts_idx.get(evt.timestamp)
        if bar is None or bar + 1 >= n:
            continue
        nxt = bar + 1
        broken = float(evt.level_or_zone)
        drn    = "long" if evt.direction == Direction.BULLISH else "short"
        ep     = opens[nxt]
        sl     = broken * (1 - SL_BUFFER) if drn == "long" else broken * (1 + SL_BUFFER)
        risk   = abs(ep - sl)
        if risk <= 0:
            continue
        tp = (ep + RR * risk) if drn == "long" else (ep - RR * risk)
        signals.append(dict(entry_idx=nxt, entry_time=df.index[nxt],
                            direction=drn, entry_price=ep,
                            sl_price=sl, tp_price=tp))

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_fvg(events: List[IndicatorEvent], df: pd.DataFrame) -> List[Dict]:
    """
    FVG return-to-gap entry.
    Rule: after FVG forms, enter at first close that is inside the gap.
    SL  = gap opposite edge ± buf
    TP  = 2R
    """
    ts_idx  = _ts_index(df)
    highs   = df["high"].to_numpy(float)
    lows    = df["low"].to_numpy(float)
    closes  = df["close"].to_numpy(float)
    n       = len(df)
    signals = []
    seen    = set()

    for evt in events:
        if evt.event_type != EventType.FVG_ACTIVE:
            continue
        key = evt.event_key()
        if key in seen:
            continue
        seen.add(key)

        formed = ts_idx.get(evt.timestamp)
        if formed is None:
            continue
        fvg_bot, fvg_top = evt.level_or_zone
        drn = "long" if evt.direction == Direction.BULLISH else "short"

        for i in range(formed + 1, min(formed + 300, n)):
            if lows[i] <= fvg_top and highs[i] >= fvg_bot:
                ep = closes[i]
                if drn == "long":
                    sl   = fvg_bot * (1 - SL_BUFFER)
                    risk = ep - sl
                    if risk <= 0:
                        continue
                    tp = ep + RR * risk
                else:
                    sl   = fvg_top * (1 + SL_BUFFER)
                    risk = sl - ep
                    if risk <= 0:
                        continue
                    tp = ep - RR * risk
                signals.append(dict(entry_idx=i, entry_time=df.index[i],
                                    direction=drn, entry_price=ep,
                                    sl_price=sl, tp_price=tp))
                break

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_session_sweep(events: List[IndicatorEvent],
                          df: pd.DataFrame) -> List[Dict]:
    """
    Session Sweep next-bar-open entry.
    Rule: sweep bar confirmed → enter next bar open.
    SL  = swept session level (the wick extreme)
    TP  = 2R
    """
    ts_idx  = _ts_index(df)
    opens   = df["open"].to_numpy(float)
    n       = len(df)
    signals = []

    for evt in events:
        if evt.event_type != EventType.SESSION_SWEEP or evt.state != EventState.ACTIVE:
            continue
        bar = ts_idx.get(evt.timestamp)
        if bar is None or bar + 1 >= n:
            continue
        nxt   = bar + 1
        level = float(evt.level_or_zone)
        drn   = "long" if evt.direction == Direction.BULLISH else "short"
        ep    = opens[nxt]
        sl    = level * (1 - SL_BUFFER) if drn == "long" else level * (1 + SL_BUFFER)
        risk  = abs(ep - sl)
        if risk <= 0:
            continue
        tp = (ep + RR * risk) if drn == "long" else (ep - RR * risk)
        signals.append(dict(entry_idx=nxt, entry_time=df.index[nxt],
                            direction=drn, entry_price=ep,
                            sl_price=sl, tp_price=tp))

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_engulfing(events: List[IndicatorEvent],
                      df: pd.DataFrame) -> List[Dict]:
    """
    Engulfing candle next-bar-open entry.
    Rule: engulfing bar confirmed → enter next bar open.
    SL  = engulfing bar low  (long)  or  high  (short)
    TP  = 2R
    """
    ts_idx  = _ts_index(df)
    opens   = df["open"].to_numpy(float)
    highs   = df["high"].to_numpy(float)
    lows    = df["low"].to_numpy(float)
    n       = len(df)
    signals = []

    for evt in events:
        if evt.event_type != EventType.ENGULFING:
            continue
        bar = ts_idx.get(evt.timestamp)
        if bar is None or bar + 1 >= n:
            continue
        nxt  = bar + 1
        drn  = "long" if evt.direction == Direction.BULLISH else "short"
        ep   = opens[nxt]
        sl   = lows[bar] * (1 - SL_BUFFER) if drn == "long" else highs[bar] * (1 + SL_BUFFER)
        risk = abs(ep - sl)
        if risk <= 0:
            continue
        tp = (ep + RR * risk) if drn == "long" else (ep - RR * risk)
        signals.append(dict(entry_idx=nxt, entry_time=df.index[nxt],
                            direction=drn, entry_price=ep,
                            sl_price=sl, tp_price=tp))

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_liquidity_pool(events: List[IndicatorEvent],
                           df: pd.DataFrame) -> List[Dict]:
    """
    Liquidity Pool counter-sweep entry.
    Rule: after buyside pool is swept → short (counter-sweep);
          after sellside pool swept    → long.
    SL  = pool level ± buf
    TP  = 2R
    """
    ts_idx  = _ts_index(df)
    opens   = df["open"].to_numpy(float)
    n       = len(df)
    signals = []

    for evt in events:
        if evt.event_type != EventType.LIQUIDITY_POOL_SWEPT:
            continue
        bar = ts_idx.get(evt.timestamp)
        if bar is None or bar + 1 >= n:
            continue
        nxt   = bar + 1
        level = float(evt.level_or_zone)
        # Counter-sweep: buyside swept (bulls stopped out) → short
        drn   = "short" if evt.direction == Direction.BULLISH else "long"
        ep    = opens[nxt]
        sl    = level * (1 - SL_BUFFER) if drn == "long" else level * (1 + SL_BUFFER)
        risk  = abs(ep - sl)
        if risk <= 0:
            continue
        tp = (ep + RR * risk) if drn == "long" else (ep - RR * risk)
        signals.append(dict(entry_idx=nxt, entry_time=df.index[nxt],
                            direction=drn, entry_price=ep,
                            sl_price=sl, tp_price=tp))

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_ote(events: List[IndicatorEvent], df: pd.DataFrame) -> List[Dict]:
    """
    OTE zone entry at bar close.
    Rule: bar close enters 62–79 % Fib zone → enter at that close.
    SL  = swing extreme (swing_low for long, swing_high for short) ± buf
    TP  = 2R
    """
    ts_idx  = _ts_index(df)
    closes  = df["close"].to_numpy(float)
    n       = len(df)
    signals = []

    for evt in events:
        if evt.event_type != EventType.OTE_ENTERED:
            continue
        bar = ts_idx.get(evt.timestamp)
        if bar is None:
            continue
        drn = "long" if evt.direction == Direction.BULLISH else "short"
        ep  = closes[bar]
        sh  = float(evt.metadata.get("swing_high", 0))
        sl_ = float(evt.metadata.get("swing_low", 0))

        if drn == "long":
            sl   = sl_ * (1 - SL_BUFFER)
            risk = ep - sl
        else:
            sl   = sh * (1 + SL_BUFFER)
            risk = sl - ep

        # Sanity: risk must be positive and < 5 % of price
        if risk <= 0 or risk > ep * 0.05:
            continue
        tp = (ep + RR * risk) if drn == "long" else (ep - RR * risk)
        signals.append(dict(entry_idx=bar, entry_time=df.index[bar],
                            direction=drn, entry_price=ep,
                            sl_price=sl, tp_price=tp))

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_prev_hl(events: List[IndicatorEvent], df: pd.DataFrame) -> List[Dict]:
    """
    Previous period High/Low breakout entry.
    Rule: bar breaks prior H → long next bar open; breaks prior L → short.
    SL  = broken level (now support/resistance)
    TP  = 2R
    """
    ts_idx  = _ts_index(df)
    opens   = df["open"].to_numpy(float)
    n       = len(df)
    signals = []

    for evt in events:
        if evt.event_type not in (EventType.PREV_HIGH_BROKEN,
                                  EventType.PREV_LOW_BROKEN):
            continue
        bar = ts_idx.get(evt.timestamp)
        if bar is None or bar + 1 >= n:
            continue
        nxt   = bar + 1
        level = float(evt.level_or_zone)
        drn   = "long" if evt.event_type == EventType.PREV_HIGH_BROKEN else "short"
        ep    = opens[nxt]
        sl    = level * (1 - SL_BUFFER) if drn == "long" else level * (1 + SL_BUFFER)
        risk  = abs(ep - sl)
        if risk <= 0:
            continue
        tp = (ep + RR * risk) if drn == "long" else (ep - RR * risk)
        signals.append(dict(entry_idx=nxt, entry_time=df.index[nxt],
                            direction=drn, entry_price=ep,
                            sl_price=sl, tp_price=tp))

    return sorted(signals, key=lambda x: x["entry_idx"])


def signals_breaker(events: List[IndicatorEvent], df: pd.DataFrame) -> List[Dict]:
    """
    Breaker Block retest entry.
    Rule: price re-enters original OB zone (now flipped) → enter next bar open.
    SL  = bottom of zone (bull breaker) or top of zone (bear breaker) ± buf
    TP  = 2R
    """
    ts_idx  = _ts_index(df)
    opens   = df["open"].to_numpy(float)
    n       = len(df)
    signals = []

    for evt in events:
        if evt.event_type != EventType.BREAKER_BLOCK_RETESTED:
            continue
        bar = ts_idx.get(evt.timestamp)
        if bar is None or bar + 1 >= n:
            continue
        nxt       = bar + 1
        b_bot, b_top = evt.level_or_zone
        drn       = "long" if evt.direction == Direction.BULLISH else "short"
        ep        = opens[nxt]
        sl        = b_bot * (1 - SL_BUFFER) if drn == "long" else b_top * (1 + SL_BUFFER)
        risk      = abs(ep - sl)
        if risk <= 0:
            continue
        tp = (ep + RR * risk) if drn == "long" else (ep - RR * risk)
        signals.append(dict(entry_idx=nxt, entry_time=df.index[nxt],
                            direction=drn, entry_price=ep,
                            sl_price=sl, tp_price=tp))

    return sorted(signals, key=lambda x: x["entry_idx"])


# ══════════════════════════════════════════════════════════════════════════════
# COMBINATION FILTER
# ══════════════════════════════════════════════════════════════════════════════

def filter_by_combo(primary: List[Dict], secondary: List[Dict],
                    window: int = COMBO_WIN) -> List[Dict]:
    """
    Keep only primary signals that have a same-direction secondary signal
    within ±window bars.
    """
    # Build secondary lookup: idx → set of directions
    sec_map: Dict[int, set] = {}
    for sig in secondary:
        idx = int(sig["entry_idx"])
        sec_map.setdefault(idx, set()).add(sig["direction"])

    result = []
    for sig in primary:
        idx = int(sig["entry_idx"])
        drn = sig["direction"]
        for offset in range(-window, window + 1):
            if drn in sec_map.get(idx + offset, set()):
                result.append(sig)
                break
    return result


# ══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

# Each entry: (label, tf, detect_fn, signal_fn)
# detect_fn signature: detect_fn(df, tf) -> List[IndicatorEvent]
# signal_fn signature: signal_fn(events, df) -> List[Dict]

INDIVIDUAL_EXPERIMENTS: List[Tuple] = [
    # ── Order Blocks ──────────────────────────────────────────────────────────
    ("OB_M5",  "M5",
     lambda df, tf: detect_order_blocks(df, timeframe=tf),
     signals_ob),
    ("OB_M15", "M15",
     lambda df, tf: detect_order_blocks(df, timeframe=tf),
     signals_ob),
    ("OB_H1",  "H1",
     lambda df, tf: detect_order_blocks(df, timeframe=tf),
     signals_ob),

    # ── Change of Character (CHoCH) ───────────────────────────────────────────
    ("CHoCH_M5",  "M5",
     lambda df, tf: detect_market_structure(df, timeframe=tf),
     lambda evts, df: signals_structure(evts, df, EventType.CHOCH)),
    ("CHoCH_M15", "M15",
     lambda df, tf: detect_market_structure(df, timeframe=tf),
     lambda evts, df: signals_structure(evts, df, EventType.CHOCH)),
    ("CHoCH_H1",  "H1",
     lambda df, tf: detect_market_structure(df, timeframe=tf),
     lambda evts, df: signals_structure(evts, df, EventType.CHOCH)),

    # ── Break of Structure (BOS) ──────────────────────────────────────────────
    ("BOS_M5",  "M5",
     lambda df, tf: detect_market_structure(df, timeframe=tf),
     lambda evts, df: signals_structure(evts, df, EventType.BOS)),
    ("BOS_M15", "M15",
     lambda df, tf: detect_market_structure(df, timeframe=tf),
     lambda evts, df: signals_structure(evts, df, EventType.BOS)),
    ("BOS_H1",  "H1",
     lambda df, tf: detect_market_structure(df, timeframe=tf),
     lambda evts, df: signals_structure(evts, df, EventType.BOS)),

    # ── Fair Value Gaps ───────────────────────────────────────────────────────
    ("FVG_M5",  "M5",
     lambda df, tf: detect_fvg(df, timeframe=tf),
     signals_fvg),
    ("FVG_M15", "M15",
     lambda df, tf: detect_fvg(df, timeframe=tf),
     signals_fvg),
    ("FVG_H1",  "H1",
     lambda df, tf: detect_fvg(df, timeframe=tf),
     signals_fvg),

    # ── Session Sweep ─────────────────────────────────────────────────────────
    ("SessionSweep_M5",  "M5",
     lambda df, tf: detect_session_sweep(df, timeframe=tf),
     signals_session_sweep),
    ("SessionSweep_M15", "M15",
     lambda df, tf: detect_session_sweep(df, timeframe=tf),
     signals_session_sweep),

    # ── Engulfing ─────────────────────────────────────────────────────────────
    ("Engulfing_M5",  "M5",
     lambda df, tf: detect_engulfing(df, timeframe=tf),
     signals_engulfing),
    ("Engulfing_M15", "M15",
     lambda df, tf: detect_engulfing(df, timeframe=tf),
     signals_engulfing),
    ("Engulfing_H1",  "H1",
     lambda df, tf: detect_engulfing(df, timeframe=tf),
     signals_engulfing),

    # ── Liquidity Pools ───────────────────────────────────────────────────────
    ("LiqPool_M15", "M15",
     lambda df, tf: detect_liquidity_pools(df, timeframe=tf),
     signals_liquidity_pool),
    ("LiqPool_H1",  "H1",
     lambda df, tf: detect_liquidity_pools(df, timeframe=tf),
     signals_liquidity_pool),

    # ── Optimal Trade Entry (Fibonacci OTE) ───────────────────────────────────
    ("OTE_M15", "M15",
     lambda df, tf: detect_ote(df, timeframe=tf),
     signals_ote),
    ("OTE_H1",  "H1",
     lambda df, tf: detect_ote(df, timeframe=tf),
     signals_ote),

    # ── Previous Period High / Low ────────────────────────────────────────────
    ("PrevHL_H1",  "H1",
     lambda df, tf: detect_prev_high_low(df, timeframe=tf, period="1D"),
     signals_prev_hl),
    ("PrevHL_H4",  "H4",
     lambda df, tf: detect_prev_high_low(df, timeframe=tf, period="1D"),
     signals_prev_hl),

    # ── Breaker Blocks ────────────────────────────────────────────────────────
    ("BreakerBlock_M15", "M15",
     lambda df, tf: detect_breaker_blocks(df, timeframe=tf),
     signals_breaker),
    ("BreakerBlock_H1",  "H1",
     lambda df, tf: detect_breaker_blocks(df, timeframe=tf),
     signals_breaker),
]

# Combination experiments: (label, tf, primary_detect, primary_sig,
#                                      secondary_detect, secondary_sig)
COMBO_EXPERIMENTS: List[Tuple] = [
    (
        "OB+CHoCH_M15", "M15",
        lambda df, tf: detect_order_blocks(df, timeframe=tf),     signals_ob,
        lambda df, tf: detect_market_structure(df, timeframe=tf),
        lambda evts, df: signals_structure(evts, df, EventType.CHOCH),
    ),
    (
        "OB+Engulfing_M15", "M15",
        lambda df, tf: detect_order_blocks(df, timeframe=tf),     signals_ob,
        lambda df, tf: detect_engulfing(df, timeframe=tf),         signals_engulfing,
    ),
    (
        "SessionSweep+CHoCH_M15", "M15",
        lambda df, tf: detect_session_sweep(df, timeframe=tf),    signals_session_sweep,
        lambda df, tf: detect_market_structure(df, timeframe=tf),
        lambda evts, df: signals_structure(evts, df, EventType.CHOCH),
    ),
    (
        "SessionSweep+Engulfing_M15", "M15",
        lambda df, tf: detect_session_sweep(df, timeframe=tf),    signals_session_sweep,
        lambda df, tf: detect_engulfing(df, timeframe=tf),         signals_engulfing,
    ),
    (
        "OB+BOS_M15", "M15",
        lambda df, tf: detect_order_blocks(df, timeframe=tf),     signals_ob,
        lambda df, tf: detect_market_structure(df, timeframe=tf),
        lambda evts, df: signals_structure(evts, df, EventType.BOS),
    ),
    (
        "CHoCH+Engulfing_M15", "M15",
        lambda df, tf: detect_market_structure(df, timeframe=tf),
        lambda evts, df: signals_structure(evts, df, EventType.CHOCH),
        lambda df, tf: detect_engulfing(df, timeframe=tf),         signals_engulfing,
    ),
    (
        "OB+CHoCH_M5", "M5",
        lambda df, tf: detect_order_blocks(df, timeframe=tf),     signals_ob,
        lambda df, tf: detect_market_structure(df, timeframe=tf),
        lambda evts, df: signals_structure(evts, df, EventType.CHOCH),
    ),
    (
        "SessionSweep+Engulfing_M5", "M5",
        lambda df, tf: detect_session_sweep(df, timeframe=tf),    signals_session_sweep,
        lambda df, tf: detect_engulfing(df, timeframe=tf),         signals_engulfing,
    ),
    (
        "OB+FVG_M15", "M15",
        lambda df, tf: detect_order_blocks(df, timeframe=tf),     signals_ob,
        lambda df, tf: detect_fvg(df, timeframe=tf),               signals_fvg,
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# HTML REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def _verdict_color(verdict: str) -> str:
    if verdict.startswith("PASS"):
        return "#00ff88"
    if verdict == "INSUFFICIENT_DATA":
        return "#888888"
    return "#ff4444"


def _sharpe_bar(sharpe: float) -> str:
    w = min(int(abs(sharpe) / 8.0 * 100), 100)
    c = "#00ff88" if sharpe >= 0.5 else "#ff4444"
    return (f'<div style="background:#222;border-radius:3px;height:8px;width:120px;">'
            f'<div style="background:{c};height:8px;width:{w}%;border-radius:3px;"></div></div>')


def generate_html_report(
    all_metrics: List[Dict[str, Any]],
    run_date: str,
) -> str:
    # Sort by sharpe descending
    rows = sorted(all_metrics, key=lambda x: x["sharpe"], reverse=True)

    pass_count = sum(1 for r in rows if r["verdict"].startswith("PASS"))
    fail_count = len(rows) - pass_count

    best = rows[0] if rows else {}

    def row_html(r: Dict) -> str:
        vc      = _verdict_color(r["verdict"])
        bar     = _sharpe_bar(r["sharpe"])
        avg_c   = "#00ff88" if r["avg_r"]   >= 0 else "#ff4444"
        tot_c   = "#00ff88" if r["total_r"] >= 0 else "#ff4444"
        return (
            f'<tr>'
            f'<td style="font-weight:bold;color:#ffd700">{r["experiment"]}</td>'
            f'<td>{r["timeframe"]}</td>'
            f'<td>{r["trades"]}</td>'
            f'<td>{r["win_rate"]}%</td>'
            f'<td style="color:{avg_c}">'
            f'{r["avg_r"]:+.3f}</td>'
            f'<td style="color:{tot_c}">'
            f'{r["total_r"]:+.1f}</td>'
            f'<td>{r["profit_factor"]:.2f}</td>'
            f'<td>{bar}&nbsp;{r["sharpe"]:.2f}</td>'
            f'<td style="color:#ff9900">{r["max_dd_r"]:.1f}R</td>'
            f'<td style="color:{vc};font-weight:bold">{r["verdict"][:40]}</td>'
            f'<td style="color:#888;font-size:11px">{r["date_start"]}→{r["date_end"]}</td>'
            f'</tr>'
        )

    rows_html = "\n".join(row_html(r) for r in rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Indicator Research Matrix — Solid2026</title>
<style>
  :root {{
    --bg-primary: #0a0a0f;
    --bg-card: #12121a;
    --bg-table-header: #1a1a28;
    --gold: #ffd700;
    --green: #00ff88;
    --red: #ff4444;
    --text: #e0e0e0;
    --muted: #888;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg-primary); color: var(--text);
          font-family: 'Inter', monospace; font-size: 13px; }}
  .hero {{
    background: linear-gradient(135deg, #0a0a0f 0%, #1a1228 50%, #0a0f1a 100%);
    padding: 40px 48px 32px;
    border-bottom: 1px solid #2a2a3a;
  }}
  .hero h1 {{ font-size: 28px; color: var(--gold); letter-spacing: 1px; }}
  .hero p  {{ color: var(--muted); margin-top: 6px; font-size: 13px; }}
  .kpi-strip {{
    display: flex; gap: 20px; padding: 20px 48px;
    background: var(--bg-card); border-bottom: 1px solid #1a1a2e;
    flex-wrap: wrap;
  }}
  .kpi {{ background: #1a1a28; border: 1px solid #2a2a3a;
           border-radius: 8px; padding: 14px 20px; min-width: 140px; }}
  .kpi .val {{ font-size: 22px; font-weight: bold; color: var(--gold); }}
  .kpi .lbl {{ font-size: 11px; color: var(--muted); margin-top: 3px; }}
  .section {{ padding: 24px 48px; }}
  h2 {{ font-size: 16px; color: var(--gold); margin-bottom: 16px;
        border-left: 3px solid var(--gold); padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: var(--bg-table-header); color: var(--muted);
        text-align: left; padding: 8px 10px; border-bottom: 1px solid #2a2a3a;
        font-weight: 600; text-transform: uppercase; font-size: 10px;
        letter-spacing: 0.5px; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #16161f; }}
  tr:hover td {{ background: #14141e; }}
  .gates {{ background: var(--bg-card); border: 1px solid #2a2a3a;
             border-radius: 8px; padding: 16px 20px; margin-top: 12px;
             font-size: 12px; color: var(--muted); }}
  .gates span {{ color: var(--text); }}
  footer {{ padding: 20px 48px; color: var(--muted); font-size: 11px;
             border-top: 1px solid #1a1a2e; margin-top: 24px; }}
</style>
</head>
<body>

<div class="hero">
  <h1>Indicator Research Matrix — XAUUSD</h1>
  <p>Solid2026 | Falsification-first ICT indicator testing |
     Full history D:\\.openclaw\\GoldBacktesting\\bars\\ | {run_date}</p>
</div>

<div class="kpi-strip">
  <div class="kpi"><div class="val">{len(rows)}</div><div class="lbl">Experiments run</div></div>
  <div class="kpi"><div class="val" style="color:var(--green)">{pass_count}</div>
    <div class="lbl">PASS</div></div>
  <div class="kpi"><div class="val" style="color:var(--red)">{fail_count}</div>
    <div class="lbl">FAIL / INSUF</div></div>
  <div class="kpi"><div class="val">{best.get('experiment','—')}</div>
    <div class="lbl">Top experiment</div></div>
  <div class="kpi"><div class="val" style="color:var(--green)">{best.get('sharpe',0):.2f}</div>
    <div class="lbl">Best Sharpe</div></div>
  <div class="kpi"><div class="val">{best.get('profit_factor',0):.2f}</div>
    <div class="lbl">Best PF</div></div>
</div>

<div class="section">
  <h2>Leaderboard — all experiments ranked by Sharpe</h2>
  <table>
    <thead>
      <tr>
        <th>Experiment</th><th>TF</th><th>Trades</th><th>Win%</th>
        <th>Avg R</th><th>Total R</th><th>PF</th><th>Sharpe</th>
        <th>Max DD</th><th>Verdict</th><th>Period</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Falsification Gates</h2>
  <div class="gates">
    All five gates must pass for PASS verdict:<br><br>
    <span>Trades ≥ {GATES['min_trades']}</span> &nbsp;|&nbsp;
    <span>Sharpe ≥ {GATES['min_sharpe']}</span> &nbsp;|&nbsp;
    <span>PF ≥ {GATES['min_pf']}</span> &nbsp;|&nbsp;
    <span>Max DD ≥ {GATES['max_mdd_r']}R</span> &nbsp;|&nbsp;
    <span>Win Rate ≥ {GATES['min_wr']}%</span>
    <br><br>
    R:R fixed at {RR} for all experiments.
    SL buffer: {SL_BUFFER*100:.1f}% beyond zone edge.
    Max hold: {MAX_HOLD} bars (timeout = partial R).
    Combo window: ±{COMBO_WIN} bars for two-indicator confluence.
  </div>
</div>

<footer>
  Generated by scripts/run_indicator_research.py | Solid2026 |
  Indicators: K's Python stack (order_blocks_mtf_v2, market_structure_v1,
  fvg_detector, sessions_model, engulfing_pro_v1, liquidity_pools, ote_tracker,
  prev_high_low, breaker_blocks, confluence_scorer)
</footer>

</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_single(label: str, tf: str,
               detect_fn: Callable, signal_fn: Callable) -> Tuple[Dict, List[Trade]]:
    print(f"\n  ── {label} ({tf}) ──")
    df     = load_bars(tf)
    events = detect_fn(df, tf)
    sigs   = signal_fn(events, df)
    print(f"     events={len(events)}  signals={len(sigs)}")
    trades = run_backtest(df, sigs)
    print(f"     trades={len(trades)}")
    metrics = compute_metrics(trades, label, tf)
    print(f"     {metrics['verdict']}  sharpe={metrics['sharpe']:.2f}  "
          f"pf={metrics['profit_factor']:.2f}  wr={metrics['win_rate']:.1f}%")
    return metrics, trades


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_metrics: List[Dict]  = []
    all_trades:  Dict[str, List[Trade]] = {}

    # ── Phase 1: Individual experiments ──────────────────────────────────────
    print("\n" + "="*70)
    print("PHASE 1 — INDIVIDUAL INDICATOR EXPERIMENTS")
    print("="*70)

    for entry in INDIVIDUAL_EXPERIMENTS:
        label, tf, detect_fn, signal_fn = entry
        try:
            metrics, trades = run_single(label, tf, detect_fn, signal_fn)
        except Exception as exc:
            print(f"     ERROR: {exc}")
            import traceback; traceback.print_exc()
            metrics = dict(experiment=label, timeframe=tf, trades=0,
                           win_rate=0, avg_r=0, total_r=0,
                           profit_factor=0, sharpe=0, max_dd_r=0,
                           verdict=f"ERROR: {exc}", date_start="", date_end="")
            trades  = []
        all_metrics.append(metrics)
        all_trades[label] = trades

    # ── Phase 2: Combination experiments ─────────────────────────────────────
    print("\n" + "="*70)
    print("PHASE 2 — COMBINATION EXPERIMENTS (±8-bar confluence window)")
    print("="*70)

    for entry in COMBO_EXPERIMENTS:
        label, tf, p_det, p_sig, s_det, s_sig = entry
        try:
            print(f"\n  ── {label} ({tf}) ──")
            df      = load_bars(tf)
            p_evts  = p_det(df, tf)
            p_sigs  = p_sig(p_evts, df)
            s_evts  = s_det(df, tf)
            s_sigs  = s_sig(s_evts, df)
            combo   = filter_by_combo(p_sigs, s_sigs, COMBO_WIN)
            print(f"     primary={len(p_sigs)}  secondary={len(s_sigs)}  "
                  f"after_filter={len(combo)}")
            trades  = run_backtest(df, combo)
            print(f"     trades={len(trades)}")
            metrics = compute_metrics(trades, label, tf)
            print(f"     {metrics['verdict']}  sharpe={metrics['sharpe']:.2f}  "
                  f"pf={metrics['profit_factor']:.2f}  wr={metrics['win_rate']:.1f}%")
        except Exception as exc:
            print(f"     ERROR: {exc}")
            import traceback; traceback.print_exc()
            metrics = dict(experiment=label, timeframe=tf, trades=0,
                           win_rate=0, avg_r=0, total_r=0,
                           profit_factor=0, sharpe=0, max_dd_r=0,
                           verdict=f"ERROR: {exc}", date_start="", date_end="")
            trades  = []
        all_metrics.append(metrics)
        all_trades[label] = trades

    # ── Save leaderboard CSV ──────────────────────────────────────────────────
    lb_path = RESULTS_DIR / "leaderboard.csv"
    pd.DataFrame(all_metrics).sort_values("sharpe", ascending=False).to_csv(
        lb_path, index=False)
    print(f"\n  Leaderboard → {lb_path}")

    # ── Save per-experiment trade CSVs ────────────────────────────────────────
    for label, trades in all_trades.items():
        if not trades:
            continue
        safe = label.replace("/", "_").replace("+", "_plus_")
        path = RESULTS_DIR / f"{safe}_trades.csv"
        pd.DataFrame([asdict(t) for t in trades]).to_csv(path, index=False)

    # ── Generate HTML report ──────────────────────────────────────────────────
    from datetime import datetime
    run_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html_report(all_metrics, run_date)
    html_path = RESULTS_DIR / "indicator_research_report.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"  HTML report → {html_path}")

    # ── Print final summary ───────────────────────────────────────────────────
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    sorted_m = sorted(all_metrics, key=lambda x: x["sharpe"], reverse=True)
    passes = [m for m in sorted_m if m["verdict"].startswith("PASS")]
    print(f"\n  Total experiments: {len(all_metrics)}")
    print(f"  PASS: {len(passes)}")
    print(f"  FAIL/other: {len(all_metrics) - len(passes)}")

    if passes:
        print("\n  ── Passing experiments ──")
        for m in passes:
            print(f"    {m['experiment']:35s} {m['timeframe']:4s}  "
                  f"trades={m['trades']:4d}  Sharpe={m['sharpe']:5.2f}  "
                  f"PF={m['profit_factor']:4.2f}  WR={m['win_rate']:4.1f}%  "
                  f"TotalR={m['total_r']:+.1f}")

    print(f"\n  Output directory: {RESULTS_DIR}")
    print(f"  Leaderboard:      {lb_path}")
    print(f"  HTML report:      {html_path}")


if __name__ == "__main__":
    main()
