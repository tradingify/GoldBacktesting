"""
ICT Full Confluence Backtest — M5 Base TF
==========================================
Runs the complete ICT confluence model on historical XAUUSD M5 data.
This is the live-model-parity backtest: base TF = M5, matching K's k_scanner_v2.py.

Pipeline:
  1. BarProcessor labels all M5 bars with confluence scores (full TF stack).
  2. Resulting EventRegistry is passed into ICTConfluenceStrategy.
  3. NautilusTrader BacktestEngine executes trades on M5 bars (OOS window).
  4. Scorecard + HTML report saved to results/raw_runs/ICT_FULL_BACKTEST_M5/.

TF stack: M5 + M15 + M30 + H1 + H4 + D1  (matches live system exactly)
Indicators: OB, MarketStructure, FVG, LiquidityPools, Engulfing, OTE,
            PrevHL, BreakerBlocks, SessionSweep (Gate B — added 2026-03-12)

Experiment grid:
  Run 1 — Baseline  : min_score=6, rr=2.0, atr_sl_mult=1.0  (live system params)
  Run 2 — High Conv : min_score=8, rr=2.0, atr_sl_mult=1.0  (high-conviction only)
  Run 3 — Wide TP   : min_score=6, rr=3.0, atr_sl_mult=1.0  (wider take-profit)

Data:
  Full dataset : 2025-01-14 → 2026-03-04 (~60,000+ M5 bars)
  OOS start    : 2025-09-11  (6-month validation window, ~12,274 M15 equiv bars)
  Bars dir     : D:\\.openclaw\\GoldBacktesting\\bars\\

Falsification gates (Sprint 04 standard):
  min_trades >= 30, Sharpe > 0.5, PF > 1.0, MDD > -20%, Win Rate > 35%

Usage:
  $env:PYTHONPATH="D:\\.openclaw\\GoldBacktesting\\Solid2026"
  python scripts/run_ict_full_backtest_m5.py

Parity notes (known gaps vs live system):
  - Engulfing: Solid2026 counts unconditionally; K gates it on OB/sweep context.
    Net effect: more signals expected.
  - OB mitigation: live system mitigates each TF's OBs on that TF's own bars.
    Solid2026 mitigates per indicator run (same net effect, see order_blocks.py).
  - Session sweep TTL: 8 hours (K checks last 5 M15 bars = ~75 min).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")

import pandas as pd
import numpy as np

from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.data.ingest.bar_builder import df_to_nautilus_bars
from src.gold_research.analytics.scorecards import StrategyScorecard
from src.gold_research.analytics.metrics import sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.pipeline.bar_processor import BarProcessor
from src.gold_research.pipeline.event_registry import EventRegistry
from src.gold_research.strategies.ict.confluence_strategy import (
    ICTConfluenceConfig,
    ICTConfluenceStrategy,
)

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.objects import Price, Quantity, Money, Currency
from nautilus_trader.config import LoggingConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("ict_full_backtest_m5")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL       = "XAUUSD"
BASE_TF      = "M5"
BARS_DIR     = Path(r"D:\.openclaw\GoldBacktesting\bars")
RAW_M5       = BARS_DIR / "xauusd_5_mins.parquet"
OOS_START    = "2025-09-11"   # 6-month out-of-sample window
RESULTS_DIR  = ProjectPaths.RESULTS / "raw_runs" / "ICT_FULL_BACKTEST_M5"

EXPERIMENTS = [
    {
        "run_id":     "run_ICT_m5_score6_rr2",
        "label":      "ICT M5 Baseline (score≥6, RR 2.0)",
        "params":     {"min_fire_score": 6, "rr": 2.0, "atr_sl_mult": 1.0, "atr_window": 14},
        "hypothesis": "Full ICT confluence (score≥6) at M5, matching live scanner params",
    },
    {
        "run_id":     "run_ICT_m5_score8_rr2",
        "label":      "ICT M5 High Conviction (score≥8, RR 2.0)",
        "params":     {"min_fire_score": 8, "rr": 2.0, "atr_sl_mult": 1.0, "atr_window": 14},
        "hypothesis": "High-conviction-only ICT signals (K's '8+ with engulfing' threshold)",
    },
    {
        "run_id":     "run_ICT_m5_score6_rr3",
        "label":      "ICT M5 Wide TP (score≥6, RR 3.0)",
        "params":     {"min_fire_score": 6, "rr": 3.0, "atr_sl_mult": 1.0, "atr_window": 14},
        "hypothesis": "Wider take-profit to capture full ICT moves; same entry threshold",
    },
]


# ---------------------------------------------------------------------------
# Engine helpers (mirrors run_asia_sweep_15m.py pattern)
# ---------------------------------------------------------------------------

def create_engine() -> BacktestEngine:
    config = BacktestEngineConfig(
        trader_id="BACKTESTER-001",
        logging=LoggingConfig(log_level="ERROR"),
    )
    engine = BacktestEngine(config=config)
    engine.add_venue(
        venue=Venue("IDEALPRO"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=None,
        starting_balances=[Money.from_str("100000 USD")],
    )
    return engine


def add_xauusd_instrument(engine: BacktestEngine):
    instrument_id = InstrumentId(Symbol("XAUUSD"), Venue("IDEALPRO"))
    instrument = CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol("XAUUSD"),
        base_currency=Currency.from_str("XAU"),
        quote_currency=Currency.from_str("USD"),
        price_precision=2,
        size_precision=0,
        price_increment=Price(0.01, 2),
        size_increment=Quantity.from_int(1),
        multiplier=Quantity.from_int(1),
        lot_size=Quantity.from_int(1),
        max_quantity=Quantity.from_int(1_000_000),
        min_quantity=Quantity.from_int(1),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        ts_event=0,
        ts_init=0,
    )
    engine.add_instrument(instrument)
    return instrument


def build_scorecard(engine: BacktestEngine, run_id: str) -> StrategyScorecard:
    """Extract performance metrics from a completed BacktestEngine."""
    try:
        positions = engine.trader.generate_positions_report()
    except Exception:
        positions = pd.DataFrame()
    try:
        fills = engine.trader.generate_order_fills_report()
    except Exception:
        fills = pd.DataFrame()

    total_trades = 0
    win_rate = profit_factor = net_profit = sharpe = sortino_val = calmar_val = mdd = 0.0
    status = "COMPLETED"

    if not positions.empty and "realized_pnl" in positions.columns:
        pnl = positions["realized_pnl"].apply(
            lambda x: float(str(x).replace(" USD", "").replace(",", "")) if pd.notna(x) else 0.0
        )
        total_trades = len(pnl)
        winners = pnl[pnl > 0]
        losers  = pnl[pnl <= 0]
        win_rate = len(winners) / total_trades if total_trades > 0 else 0.0
        gross_profit = float(winners.sum()) if len(winners) > 0 else 0.0
        gross_loss   = abs(float(losers.sum())) if len(losers) > 0 else 0.0
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )
        net_profit = gross_profit - gross_loss

        equity = pd.Series(100_000.0 + pnl.cumsum().values, dtype=float)
        if len(equity) > 1:
            returns = equity.pct_change().dropna()
            sharpe      = sharpe_ratio(returns)
            sortino_val = sortino_ratio(returns)
            mdd         = max_drawdown(equity)
            calmar_val  = calmar_ratio(returns, equity)
    elif not fills.empty:
        total_trades = len(fills) // 2
        status = "COMPLETED_LIMITED_DATA"
    else:
        status = "NO_TRADES"

    return StrategyScorecard(
        run_id=run_id,
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=min(profit_factor, 999.99),
        total_net_profit=net_profit,
        sharpe=sharpe,
        sortino=sortino_val,
        calmar=calmar_val,
        max_dd_pct=mdd,
        status=status,
    )


def falsification_checks(sc: StrategyScorecard) -> dict:
    checks = {
        "min_trades":      {"value": sc.total_trades,           "threshold": ">= 30",   "passed": sc.total_trades >= 30},
        "sharpe_positive": {"value": round(sc.sharpe, 4),       "threshold": "> 0.5",   "passed": sc.sharpe > 0.5},
        "profit_factor":   {"value": round(sc.profit_factor, 4), "threshold": "> 1.0",  "passed": sc.profit_factor > 1.0},
        "max_drawdown":    {"value": round(sc.max_dd_pct, 4),   "threshold": "> -0.20", "passed": sc.max_dd_pct > -0.20},
        "win_rate_floor":  {"value": round(sc.win_rate, 4),     "threshold": "> 0.35",  "passed": sc.win_rate > 0.35},
    }
    all_pass = all(c["passed"] for c in checks.values())
    return {"checks": checks, "verdict": "PASS" if all_pass else "FAIL", "all_pass": all_pass}


# ---------------------------------------------------------------------------
# Pre-compute event registry (shared across all experiment runs)
# ---------------------------------------------------------------------------

def build_registry(bars_dir: Path) -> tuple[EventRegistry, dict]:
    """
    Run the full ICT indicator pipeline on all M5 data and return a populated
    EventRegistry plus pipeline diagnostics.

    The registry covers the ENTIRE dataset so experiments with different
    start dates all have proper warm-up context.
    """
    logger.info("=" * 60)
    logger.info("PRE-COMPUTING ICT EVENT REGISTRY  |  base=%s", BASE_TF)
    logger.info("  TF stack: M5, M15, M30, H1, H4, D1")
    logger.info("  Indicators: 9 (OB, MS, FVG, LP, Eng, OTE, PHL, BB, SessionSweep)")
    logger.info("=" * 60)

    processor = BarProcessor(bars_dir=bars_dir, symbol=SYMBOL)
    processor.load()  # Load all TFs

    all_events = processor.run_indicators()   # All events across all TFs

    registry = EventRegistry(symbol=SYMBOL)
    registry.feed(all_events)

    # Run label_bars for diagnostics (OOS window only)
    labeled = processor.label_bars(
        base_tf=BASE_TF,
        start=OOS_START,
        end=None,
    )

    fire_rate  = labeled["fire"].mean() * 100
    mean_score = labeled["score"].mean()
    fire_count = int(labeled["fire"].sum())
    total_bars = len(labeled)

    logger.info("Pipeline stats (OOS window only):")
    logger.info("  Total bars   : %d", total_bars)
    logger.info("  Fire bars    : %d  (%.2f%%)", fire_count, fire_rate)
    logger.info("  Mean score   : %.3f", mean_score)
    logger.info("  Total events : %d", len(all_events))

    diagnostics = {
        "base_tf":      BASE_TF,
        "total_bars":   total_bars,
        "fire_bars":    fire_count,
        "fire_rate_pct": round(fire_rate, 2),
        "mean_score":   round(mean_score, 3),
        "total_events": len(all_events),
        "oos_start":    OOS_START,
    }

    # Save labeled bars for inspection
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_cols = ["open", "high", "low", "close", "volume",
                 "score", "direction", "fire", "combo", "n_events"]
    labeled[save_cols].to_parquet(RESULTS_DIR / "labeled_bars_m5.parquet")

    fire_df = labeled[labeled["fire"]][save_cols].reset_index()
    fire_df.to_csv(RESULTS_DIR / "fire_events_m5.csv", index=False)

    logger.info("Saved labeled_bars_m5.parquet and fire_events_m5.csv")

    return registry, diagnostics, labeled


# ---------------------------------------------------------------------------
# Single experiment run
# ---------------------------------------------------------------------------

def run_experiment(exp: dict, registry: EventRegistry, df_oos: pd.DataFrame) -> dict:
    """Run one backtest configuration.  Returns result dict."""
    run_id = exp["run_id"]
    logger.info("─" * 60)
    logger.info("RUNNING: %s  (%s)", exp["label"], run_id)
    logger.info("─" * 60)

    try:
        # Convert OOS M5 bars to Nautilus format
        bars = df_to_nautilus_bars(df_oos.copy(), "XAUUSD", "IDEALPRO", "5m")
        logger.info("  Bars: %d  (%s → %s)",
                    len(bars),
                    str(df_oos["datetime"].min()) if "datetime" in df_oos.columns else df_oos.index[0],
                    str(df_oos["datetime"].max()) if "datetime" in df_oos.columns else df_oos.index[-1])

        engine = create_engine()
        add_xauusd_instrument(engine)
        engine.add_data(bars)

        config = ICTConfluenceConfig(
            instrument_id="XAUUSD-IDEALPRO-USD",
            timeframe="5m",
            **exp["params"],
        )
        strategy = ICTConfluenceStrategy(config=config, registry=registry)
        engine.add_strategy(strategy)

        logger.info("  Engine running…")
        engine.run()
        logger.info("  Engine complete.")

        scorecard     = build_scorecard(engine, run_id)
        falsification = falsification_checks(scorecard)

        logger.info(
            "  Trades=%d  Sharpe=%.4f  PF=%.4f  WR=%.1f%%  MDD=%.2f%%  → %s",
            scorecard.total_trades,
            scorecard.sharpe,
            scorecard.profit_factor,
            scorecard.win_rate * 100,
            scorecard.max_dd_pct * 100,
            falsification["verdict"],
        )

        # Save run artifacts
        run_dir = RESULTS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        spec = {
            "experiment_id": "ICT_FULL_BACKTEST_M5",
            "run_id":        run_id,
            "label":         exp["label"],
            "base_tf":       BASE_TF,
            "params":        exp["params"],
            "oos_start":     OOS_START,
            "hypothesis":    exp["hypothesis"],
        }
        (run_dir / "spec.json").write_text(json.dumps(spec, indent=4, default=str))
        (run_dir / "scorecard.json").write_text(json.dumps(scorecard.model_dump(), indent=4))
        (run_dir / "falsification.json").write_text(json.dumps(falsification, indent=4))

        try:
            positions = engine.trader.generate_positions_report()
            if not positions.empty:
                positions.to_csv(run_dir / "positions.csv", index=False)
        except Exception:
            pass

        return {
            "run_id":         run_id,
            "label":          exp["label"],
            "params":         exp["params"],
            "scorecard":      scorecard.model_dump(),
            "falsification":  falsification,
            "status":         "OK",
        }

    except Exception as exc:
        logger.error("FAILED: %s — %s", run_id, exc, exc_info=True)
        return {
            "run_id":    run_id,
            "label":     exp["label"],
            "params":    exp["params"],
            "scorecard": {},
            "falsification": {"verdict": "ERROR", "all_pass": False},
            "status":    f"ERROR: {exc}",
        }


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _render_html(results: list[dict], diagnostics: dict, labeled: pd.DataFrame) -> str:
    """Generate dark-theme HTML summary report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Direction breakdown on fire bars
    fire_df = labeled[labeled["fire"]]
    bull_fires = int((fire_df["direction"] == "bullish").sum())
    bear_fires = int((fire_df["direction"] == "bearish").sum())
    total_fires = diagnostics["fire_bars"]

    # Top combos
    top_combos = (
        fire_df["combo"].value_counts().head(12).to_dict()
        if not fire_df.empty and "combo" in fire_df.columns
        else {}
    )
    combo_rows = "".join(
        f"<tr><td>{c}</td><td>{n}</td>"
        f"<td>{round(n / max(total_fires, 1) * 100, 1)}%</td></tr>"
        for c, n in top_combos.items()
    )

    # Results table rows
    def _gate(v: bool) -> str:
        cls = "pass" if v else "fail"
        sym = "✓" if v else "✗"
        return f'<span class="tag {cls}">{sym}</span>'

    result_rows = ""
    for r in results:
        sc = r.get("scorecard", {})
        fa = r.get("falsification", {})
        checks = fa.get("checks", {})
        verdict = fa.get("verdict", "—")
        vcls = "pass" if verdict == "PASS" else "fail"
        result_rows += (
            f"<tr>"
            f"<td>{r['label']}</td>"
            f"<td>{sc.get('total_trades', 0)}</td>"
            f"<td>{round(sc.get('sharpe', 0), 3)}</td>"
            f"<td>{round(sc.get('profit_factor', 0), 3)}</td>"
            f"<td>{round(sc.get('win_rate', 0) * 100, 1)}%</td>"
            f"<td>{round(sc.get('max_dd_pct', 0) * 100, 2)}%</td>"
            f"<td>{round(sc.get('total_net_profit', 0), 2)}</td>"
            f"<td>{_gate(checks.get('min_trades', {}).get('passed', False))}</td>"
            f"<td>{_gate(checks.get('sharpe_positive', {}).get('passed', False))}</td>"
            f"<td>{_gate(checks.get('profit_factor', {}).get('passed', False))}</td>"
            f"<td>{_gate(checks.get('max_drawdown', {}).get('passed', False))}</td>"
            f"<td>{_gate(checks.get('win_rate_floor', {}).get('passed', False))}</td>"
            f'<td><span class="tag {vcls}">{verdict}</span></td>'
            f"</tr>\n"
        )

    # Parity gap notes
    parity_rows = (
        "<tr><td>Engulfing gate</td><td>Solid2026: unconditional; K: only when OB/sweep active</td>"
        "<td><span class='tag warn'>PARTIAL</span></td></tr>"
        "<tr><td>Session sweep TTL</td><td>8h window vs K's last-5-bar check (~75min)</td>"
        "<td><span class='tag warn'>PARTIAL</span></td></tr>"
        "<tr><td>OB mitigation</td><td>Both use own-TF bars (functionally equivalent)</td>"
        "<td><span class='tag pass'>MATCHED</span></td></tr>"
        "<tr><td>Base TF</td><td>M5 — matches live scanner</td>"
        "<td><span class='tag pass'>MATCHED</span></td></tr>"
        "<tr><td>MIN_FIRE_SCORE</td><td>6 — matches live scanner (2026-03-12)</td>"
        "<td><span class='tag pass'>MATCHED</span></td></tr>"
        "<tr><td>SessionSweep Gate B</td><td>Wired as indicator adapter (added 2026-03-12)</td>"
        "<td><span class='tag pass'>WIRED</span></td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICT Full Backtest — {SYMBOL} M5</title>
<style>
  :root {{
    --bg-primary: #0a0a0f;
    --bg-card: #12121a;
    --bg-table: #0f0f18;
    --text-primary: #e8e8f0;
    --text-muted: #888899;
    --gold: #f0c040;
    --green: #3ddc84;
    --red: #ff4d6d;
    --blue: #4da6ff;
    --border: #2a2a3a;
    --font: 'Inter', 'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg-primary); color: var(--text-primary); font-family: var(--font); }}
  .hero {{
    background: linear-gradient(135deg, #0a0a1a 0%, #1a1030 50%, #0a1520 100%);
    padding: 48px 32px 36px;
    border-bottom: 1px solid var(--border);
  }}
  .hero h1 {{ font-size: 2rem; color: var(--gold); letter-spacing: 0.04em; }}
  .hero .subtitle {{ color: var(--text-muted); margin-top: 6px; font-size: 0.95rem; }}
  .kpi-strip {{
    display: flex; flex-wrap: wrap; gap: 16px;
    padding: 24px 32px; background: var(--bg-card);
    border-bottom: 1px solid var(--border);
  }}
  .kpi {{ flex: 1; min-width: 140px; }}
  .kpi .label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; }}
  .kpi .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; }}
  .kpi.gold .value  {{ color: var(--gold); }}
  .kpi.green .value {{ color: var(--green); }}
  .kpi.blue .value  {{ color: var(--blue); }}
  .kpi.red .value   {{ color: var(--red); }}
  .section {{ padding: 28px 32px; border-bottom: 1px solid var(--border); }}
  .section h2 {{ font-size: 1.15rem; color: var(--gold); margin-bottom: 16px; letter-spacing: 0.06em; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ background: #1e1e2a; color: var(--text-muted); font-weight: 500;
        padding: 8px 12px; text-align: left; letter-spacing: 0.05em;
        border-bottom: 1px solid var(--border); }}
  td {{ padding: 7px 12px; border-bottom: 1px solid var(--border); }}
  tr:hover td {{ background: rgba(240,192,64,0.04); }}
  .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .tag.pass {{ background: rgba(61,220,132,0.15); color: var(--green); }}
  .tag.fail {{ background: rgba(255,77,109,0.15); color: var(--red); }}
  .tag.warn {{ background: rgba(240,192,64,0.15); color: var(--gold); }}
  .overflow {{ overflow-x: auto; }}
  footer {{ padding: 20px 32px; color: var(--text-muted); font-size: 0.8rem; }}
</style>
</head>
<body>

<div class="hero">
  <h1>ICT Full Confluence Backtest — {SYMBOL} M5</h1>
  <div class="subtitle">
    OOS Period: {OOS_START} → end of data &nbsp;|&nbsp; Generated: {now}
    &nbsp;|&nbsp; Solid2026 ICT Research &nbsp;|&nbsp; 9-indicator pipeline
  </div>
</div>

<div class="kpi-strip">
  <div class="kpi gold"><div class="label">Base TF</div><div class="value">M5</div></div>
  <div class="kpi blue"><div class="label">OOS Bars</div><div class="value">{diagnostics["total_bars"]:,}</div></div>
  <div class="kpi green"><div class="label">Fire Bars</div><div class="value">{diagnostics["fire_bars"]:,}</div></div>
  <div class="kpi blue"><div class="label">Fire Rate</div><div class="value">{diagnostics["fire_rate_pct"]}%</div></div>
  <div class="kpi gold"><div class="label">Mean Score</div><div class="value">{diagnostics["mean_score"]}</div></div>
  <div class="kpi green"><div class="label">Bull Fires</div><div class="value">{bull_fires:,}</div></div>
  <div class="kpi red"><div class="label">Bear Fires</div><div class="value">{bear_fires:,}</div></div>
  <div class="kpi blue"><div class="label">Total Events</div><div class="value">{diagnostics["total_events"]:,}</div></div>
</div>

<div class="section">
  <h2>Backtest Results</h2>
  <div class="overflow">
  <table>
    <thead><tr>
      <th>Config</th><th>Trades</th><th>Sharpe</th><th>PF</th>
      <th>Win Rate</th><th>Max DD</th><th>Net P&amp;L</th>
      <th>≥30T</th><th>S&gt;0.5</th><th>PF&gt;1</th><th>DD&gt;-20%</th><th>WR&gt;35%</th>
      <th>Verdict</th>
    </tr></thead>
    <tbody>{result_rows}</tbody>
  </table>
  </div>
</div>

<div class="section">
  <h2>Top Confluence Combos (fire bars — OOS window)</h2>
  <table>
    <thead><tr><th>Combo</th><th>Count</th><th>% of fires</th></tr></thead>
    <tbody>{combo_rows}</tbody>
  </table>
</div>

<div class="section">
  <h2>Live System Parity</h2>
  <table>
    <thead><tr><th>Parameter / Logic</th><th>Notes</th><th>Status</th></tr></thead>
    <tbody>{parity_rows}</tbody>
  </table>
</div>

<div class="section">
  <h2>Anti-Lookahead Status</h2>
  <table>
    <thead><tr><th>Indicator</th><th>Status</th><th>Rule</th></tr></thead>
    <tbody>
      <tr><td>Order Blocks</td><td><span class="tag pass">CLEAN</span></td><td>Activation = next-bar open after impulse</td></tr>
      <tr><td>Market Structure</td><td><span class="tag pass">CLEAN</span></td><td>Fractals need length bars each side</td></tr>
      <tr><td>Session Sweep</td><td><span class="tag pass">CLEAN</span></td><td>Session H/L only available after session close</td></tr>
      <tr><td>FVG</td><td><span class="tag pass">CLEAN</span></td><td>Formed at bar i+1 close; mitigation from i+2</td></tr>
      <tr><td>Liquidity Pools</td><td><span class="tag pass">CLEAN</span></td><td>Swing pivots need swing_length each side</td></tr>
      <tr><td>OTE</td><td><span class="tag pass">CLEAN</span></td><td>Leg confirmed; InOTE from current close only</td></tr>
      <tr><td>Engulfing</td><td><span class="tag pass">CLEAN</span></td><td>bar[i] vs bar[i-1] only</td></tr>
      <tr><td>Breaker Blocks</td><td><span class="tag pass">CLEAN</span></td><td>Depends on confirmed OB mitigation</td></tr>
      <tr><td>Prev High/Low</td><td><span class="tag pass">CLEAN</span></td><td>Prior completed period only</td></tr>
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Next Variants</h2>
  <ol style="color:var(--text-muted);line-height:2rem;font-size:0.9rem;padding-left:1.2em;">
    <li>OB-only ablation — disable all indicators except ORDER_BLOCK_ACTIVE</li>
    <li>Session Sweep + Structure ablation — Gate B only (no OB required)</li>
    <li>Engulfing gate patch — count engulfing only when OB or sweep active</li>
    <li>Walk-forward 3-fold validation on winning config</li>
    <li>Correlation check vs GOLD_PORT_02 trade dates</li>
  </ol>
</div>

<footer>
  Generated by Solid2026 ICT Full Backtest &nbsp;|&nbsp; {SYMBOL} M5
  &nbsp;|&nbsp; OOS: {OOS_START} → end &nbsp;|&nbsp; Score threshold: 6
</footer>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 70)
    logger.info("  ICT FULL BACKTEST  |  %s  |  base=%s  |  OOS: %s →",
                SYMBOL, BASE_TF, OOS_START)
    logger.info("=" * 70)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Build EventRegistry from all historical data ──────────────────
    registry, diagnostics, labeled = build_registry(BARS_DIR)

    # ── Step 2: Load OOS M5 data for NautilusTrader ──────────────────────────
    logger.info("Loading OOS M5 bars (%s →) …", OOS_START)
    df_all = load_ib_parquet(RAW_M5)

    # Filter to OOS window only for backtesting
    # (Registry was built from ALL data for proper indicator context)
    dt_col = "datetime" if "datetime" in df_all.columns else df_all.index.name
    if "datetime" in df_all.columns:
        df_oos = df_all[df_all["datetime"] >= OOS_START].copy()
    else:
        df_oos = df_all[df_all.index >= pd.Timestamp(OOS_START, tz="UTC")].copy()

    logger.info("  OOS bars: %d", len(df_oos))

    # ── Step 3: Run experiments ───────────────────────────────────────────────
    results = []
    for exp in EXPERIMENTS:
        result = run_experiment(exp, registry, df_oos)
        results.append(result)

    # ── Step 4: Save HTML report ──────────────────────────────────────────────
    html = _render_html(results, diagnostics, labeled)
    html_path = RESULTS_DIR / "ict_full_backtest_m5_report.html"
    html_path.write_text(html, encoding="utf-8")
    logger.info("Saved HTML report: %s", html_path)

    # ── Step 5: Save experiment log ───────────────────────────────────────────
    exp_log = {
        "generated":   datetime.now(timezone.utc).isoformat(),
        "experiment":  "ICT_FULL_BACKTEST_M5",
        "base_tf":     BASE_TF,
        "oos_start":   OOS_START,
        "diagnostics": diagnostics,
        "results":     results,
    }
    (RESULTS_DIR / "experiment_log.json").write_text(
        json.dumps(exp_log, indent=2, default=str)
    )
    logger.info("Saved experiment_log.json")

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    for r in results:
        sc = r.get("scorecard", {})
        verdict = r.get("falsification", {}).get("verdict", "—")
        logger.info(
            "  %-45s  trades=%-4d  Sharpe=%-7.4f  PF=%-6.4f  WR=%-6.1f%%  MDD=%-7.2f%%  %s",
            r["label"],
            sc.get("total_trades", 0),
            sc.get("sharpe", 0),
            sc.get("profit_factor", 0),
            sc.get("win_rate", 0) * 100,
            sc.get("max_dd_pct", 0) * 100,
            verdict,
        )
    logger.info("")
    logger.info("Artifacts in: %s", RESULTS_DIR)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
