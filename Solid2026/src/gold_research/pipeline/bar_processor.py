"""
Bar Processor — orchestrates the multi-timeframe ICT indicator pipeline.

The BarProcessor:
  1. Loads OHLCV DataFrames for all requested timeframes from parquet files.
  2. Runs every registered indicator adapter over each timeframe's data.
  3. Feeds all resulting IndicatorEvents into an EventRegistry.
  4. Labels each bar in the base timeframe with a ConfluenceResult.

Output: a DataFrame (one row per base-TF bar) with columns:
    timestamp | open | high | low | close | volume |
    score | direction | fire | combo | n_events | events

Multi-timeframe anti-lookahead rule
------------------------------------
For a base-TF bar closing at time T, only events whose timestamp <= T are
considered.  Higher-TF bar data is only "known" after that TF's bar closes.
Example: at M15 bar T = 10:15 UTC, the H1 bar at 10:00 is complete, but
the H1 bar at 11:00 is not.  The BarProcessor handles this automatically
because each indicator emits events timestamped at THEIR bar's close, and
the EventRegistry filters by timestamp <= T.

Registered indicators (default)
---------------------------------
  Per timeframe:
    order_blocks, market_structure, fvg, liquidity_pools,
    engulfing, ote, prev_high_low (D1 only), breaker_blocks

Timeframe file naming convention
---------------------------------
  M5  → xauusd_5_mins.parquet
  M15 → xauusd_15_mins.parquet
  M30 → xauusd_30_mins.parquet
  H1  → xauusd_1_hour.parquet
  H4  → xauusd_4_hours.parquet
  D1  → xauusd_1_day.parquet
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from gold_research.indicators.breaker_blocks import detect_breaker_blocks
from gold_research.indicators.engulfing import detect_engulfing
from gold_research.indicators.fvg import detect_fvg
from gold_research.indicators.liquidity_pools import detect_liquidity_pools
from gold_research.indicators.market_structure import detect_market_structure
from gold_research.indicators.order_blocks import detect_order_blocks
from gold_research.indicators.ote import detect_ote
from gold_research.indicators.prev_high_low import detect_prev_high_low
from gold_research.indicators.session_sweep import detect_session_sweep
from gold_research.indicators.schema import ConfluenceResult, IndicatorEvent
from gold_research.pipeline.event_registry import EventRegistry

log = logging.getLogger(__name__)

# ── Timeframe → file mapping ───────────────────────────────────────────────────

TF_FILES: Dict[str, str] = {
    "M5":  "xauusd_5_mins.parquet",
    "M15": "xauusd_15_mins.parquet",
    "M30": "xauusd_30_mins.parquet",
    "H1":  "xauusd_1_hour.parquet",
    "H4":  "xauusd_4_hours.parquet",
    "D1":  "xauusd_1_day.parquet",
}

# Default: which timeframes to run for each base TF
DEFAULT_TF_STACK: Dict[str, List[str]] = {
    "M5":  ["M5", "M15", "M30", "H1", "H4", "D1"],   # M30 added for OB parity with live system
    "M15": ["M15", "M30", "H1", "H4", "D1"],
    "M30": ["M30", "H1",  "H4", "D1"],
    "H1":  ["H1",  "H4",  "D1"],
}

# IndicatorRunner signature: (df, symbol, timeframe) → List[IndicatorEvent]
IndicatorRunner = Callable[[pd.DataFrame, str, str], List[IndicatorEvent]]


def _ob_runner(df, symbol, tf):
    return detect_order_blocks(df, symbol=symbol, timeframe=tf)

def _ms_runner(df, symbol, tf):
    return detect_market_structure(df, symbol=symbol, timeframe=tf)

def _fvg_runner(df, symbol, tf):
    return detect_fvg(df, symbol=symbol, timeframe=tf)

def _lp_runner(df, symbol, tf):
    return detect_liquidity_pools(df, symbol=symbol, timeframe=tf)

def _eng_runner(df, symbol, tf):
    return detect_engulfing(df, symbol=symbol, timeframe=tf)

def _ote_runner(df, symbol, tf):
    return detect_ote(df, symbol=symbol, timeframe=tf)

def _phl_runner(df, symbol, tf):
    return detect_prev_high_low(df, symbol=symbol, timeframe=tf, period="1D")

def _bb_runner(df, symbol, tf):
    return detect_breaker_blocks(df, symbol=symbol, timeframe=tf)

def _ss_runner(df, symbol, tf):
    # Session sweeps are meaningful on intraday TFs only (M5/M15/M30).
    # Higher TF session-sweep detection would conflate multiple sweep bars.
    if tf not in ("M5", "M15", "M30"):
        return []
    return detect_session_sweep(df, symbol=symbol, timeframe=tf)


DEFAULT_RUNNERS: List[IndicatorRunner] = [
    _ob_runner,
    _ms_runner,
    _fvg_runner,
    _lp_runner,
    _eng_runner,
    _ote_runner,
    _phl_runner,
    _bb_runner,
    _ss_runner,    # Session Sweep — K's Gate B trigger (added 2026-03-12)
]


# ── Main class ─────────────────────────────────────────────────────────────────

class BarProcessor:
    """
    Multi-timeframe ICT event pipeline for research / backtesting.

    Parameters
    ----------
    bars_dir : str | Path
        Directory containing parquet bar files.
        Canonical path: D:/.openclaw/GoldBacktesting/bars/
    symbol : str
    runners : list[IndicatorRunner] | None
        Custom indicator runners.  None = use DEFAULT_RUNNERS.
    """

    def __init__(
        self,
        bars_dir: str | Path,
        symbol: str = "XAUUSD",
        runners: Optional[List[IndicatorRunner]] = None,
    ) -> None:
        self.bars_dir = Path(bars_dir)
        self.symbol   = symbol
        self.runners  = runners if runners is not None else DEFAULT_RUNNERS
        self._dfs: Dict[str, pd.DataFrame] = {}

    # ── Data loading ───────────────────────────────────────────────────────────

    def load(self, timeframes: Optional[List[str]] = None) -> None:
        """
        Load parquet files for the requested timeframes.

        Parameters
        ----------
        timeframes : list[str] | None
            e.g. ["M15", "H1", "H4", "D1"].  None = load all in TF_FILES.
        """
        tfs = timeframes or list(TF_FILES.keys())
        for tf in tfs:
            fname = TF_FILES.get(tf)
            if fname is None:
                log.warning("No file mapping for timeframe %s", tf)
                continue
            fpath = self.bars_dir / fname
            if not fpath.exists():
                log.warning("File not found: %s", fpath)
                continue
            df = pd.read_parquet(fpath)
            df.columns = [c.lower() for c in df.columns]
            if not isinstance(df.index, pd.DatetimeIndex):
                # Try to parse from known datetime-like columns in our canonical bars schema
                for col in ("datetime", "timestamp", "time", "date"):
                    if col in df.columns:
                        df = df.set_index(col)
                        break

            if not isinstance(df.index, pd.DatetimeIndex):
                raw_index = pd.Index(df.index.astype(str).str.strip())
                parsed = pd.to_datetime(raw_index, format="%Y%m%d  %H:%M:%S", errors="coerce", utc=True)
                if getattr(parsed, "isna", lambda: [])().any():
                    fallback_date = pd.to_datetime(raw_index, format="%Y%m%d", errors="coerce", utc=True)
                    parsed = parsed.where(~parsed.isna(), fallback_date)
                if getattr(parsed, "isna", lambda: [])().any():
                    fallback_generic = pd.to_datetime(raw_index, errors="coerce", utc=True)
                    parsed = parsed.where(~parsed.isna(), fallback_generic)
                if getattr(parsed, "isna", lambda: [])().any():
                    log.error("Could not build DatetimeIndex for %s", tf)
                    continue
                df.index = parsed
            else:
                df.index = pd.to_datetime(df.index, utc=True)
            # Fix negative/NaN volumes (known IB data issue)
            if "volume" in df.columns:
                df["volume"] = df["volume"].apply(
                    lambda v: max(0, int(v)) if pd.notna(v) else 0
                )
            self._dfs[tf] = df
            log.info("Loaded %s: %d bars (%s → %s)", tf, len(df), df.index[0], df.index[-1])

    # ── Indicator run ──────────────────────────────────────────────────────────

    def run_indicators(
        self,
        timeframes: Optional[List[str]] = None,
    ) -> List[IndicatorEvent]:
        """
        Run all registered indicator runners on every loaded timeframe.

        Parameters
        ----------
        timeframes : list[str] | None
            Subset of loaded timeframes to process.  None = all loaded.

        Returns
        -------
        List[IndicatorEvent]
            All events from all indicators across all timeframes, sorted by timestamp.
        """
        tfs = timeframes or list(self._dfs.keys())
        all_events: List[IndicatorEvent] = []

        for tf in tfs:
            df = self._dfs.get(tf)
            if df is None:
                log.warning("No data loaded for %s — skipping", tf)
                continue
            for runner in self.runners:
                try:
                    evts = runner(df, self.symbol, tf)
                    all_events.extend(evts)
                    log.debug("%s | %s → %d events", tf, runner.__name__, len(evts))
                except Exception as exc:  # noqa: BLE001
                    log.error("Runner %s failed on %s: %s", runner.__name__, tf, exc)

        all_events.sort(key=lambda e: e.timestamp)
        log.info("Total events generated: %d", len(all_events))
        return all_events

    # ── Label bars ────────────────────────────────────────────────────────────

    def label_bars(
        self,
        base_tf: str = "M15",
        tf_stack: Optional[List[str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Label each base-TF bar with a ConfluenceResult.

        Loads data (if not already loaded), runs indicators on all TFs in
        tf_stack, feeds events to the EventRegistry, then emits one row per
        base-TF bar.

        Parameters
        ----------
        base_tf : str
            Primary timeframe to label (e.g. "M15").
        tf_stack : list[str] | None
            Timeframes to run indicators on.
            None = use DEFAULT_TF_STACK[base_tf].
        start : str | None
            ISO date filter (inclusive).  e.g. "2025-09-01".
        end : str | None
            ISO date filter (inclusive).  e.g. "2026-01-01".

        Returns
        -------
        pd.DataFrame
            Columns:
              timestamp, open, high, low, close, volume,
              score, direction, fire, combo, n_events, events
        """
        stack = tf_stack or DEFAULT_TF_STACK.get(base_tf, [base_tf])

        # Load missing timeframes
        missing = [tf for tf in stack if tf not in self._dfs]
        if missing:
            self.load(missing)

        if base_tf not in self._dfs:
            raise ValueError(
                f"Base timeframe {base_tf!r} not loaded.  "
                f"Available: {list(self._dfs.keys())}"
            )

        # Run all indicators
        all_events = self.run_indicators(timeframes=stack)

        # Build registry
        reg = EventRegistry(symbol=self.symbol)
        reg.feed(all_events)

        # Label base-TF bars
        base_df = self._dfs[base_tf].copy()
        if start:
            base_df = base_df[base_df.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            base_df = base_df[base_df.index <= pd.Timestamp(end, tz="UTC")]

        rows = []
        for ts, bar in base_df.iterrows():
            result: ConfluenceResult = reg.confluence_at(ts, base_tf=base_tf)
            rows.append({
                "timestamp": ts,
                "open":      float(bar["open"]),
                "high":      float(bar["high"]),
                "low":       float(bar["low"]),
                "close":     float(bar["close"]),
                "volume":    float(bar.get("volume", 0)),
                "score":     result.total_score,
                "direction": result.direction.value,
                "fire":      result.fire,
                "combo":     result.combo,
                "n_events":  len(result.active_events),
                "events":    result.active_events,  # List[IndicatorEvent]
            })

        out = pd.DataFrame(rows).set_index("timestamp")
        log.info(
            "Labeled %d bars.  Fire rate: %.1f%%",
            len(out),
            out["fire"].mean() * 100,
        )
        return out

    # ── Convenience ───────────────────────────────────────────────────────────

    def run(
        self,
        base_tf: str = "M15",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Shorthand: load + label in one call.

        Equivalent to:
            processor.load()
            return processor.label_bars(base_tf, start=start, end=end)
        """
        self.load()
        return self.label_bars(base_tf=base_tf, start=start, end=end)
