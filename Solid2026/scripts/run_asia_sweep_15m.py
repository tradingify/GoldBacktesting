"""
Asia Session Sweep — XAUUSD 15m Backtest Runner
================================================
Tests the AsiaSweep strategy on all available real IBKR 15m XAUUSD data.

The strategy fires at most one trade per Asia session (01:00–05:00 UTC),
so the full dataset is used (not a 6-month slice) to maximise sample size
and trade count.

Configurations tested:
  asia_sweep_default   : sl_buffer=0.10%, rr=2.0  (baseline spec)
  asia_sweep_tight_sl  : sl_buffer=0.05%, rr=2.0  (tighter SL, less noise)
  asia_sweep_wide_rr   : sl_buffer=0.10%, rr=3.0  (wider TP, higher avg win)

Falsification gates (Sprint 04 standard):
  min_trades >= 30, Sharpe > 0.5, PF > 1.0, MDD > -20%, Win Rate > 35%

Usage:
  $env:PYTHONPATH = "D:\\.openclaw\\GoldBacktesting\\Solid2026"
  python scripts/run_asia_sweep_15m.py
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")

import pandas as pd
import numpy as np

from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.data.ingest.bar_builder import df_to_nautilus_bars
from src.gold_research.analytics.scorecards import StrategyScorecard
from src.gold_research.analytics.metrics import sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio
from src.gold_research.core.paths import ProjectPaths

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
logger = logging.getLogger("asia_sweep_15m")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_15M = Path(r"D:\.openclaw\GoldBacktesting\bars\xauusd_15_mins.parquet")
RESULTS_DIR = ProjectPaths.RESULTS / "raw_runs" / "ASIA_SWEEP_15M"
REPORT_PATH = RESULTS_DIR / "asia_sweep_15m_report.html"

# ---------------------------------------------------------------------------
# Experiment definitions
# ---------------------------------------------------------------------------
EXPERIMENTS = [
    {
        "run_id": "run_AsiaSweep_15m_default",
        "label": "AsiaSweep Default",
        "class_path": "src.gold_research.strategies.session.asia_session_sweep.AsiaSweep",
        "config_class_path": "src.gold_research.strategies.session.asia_session_sweep.AsiaSweepConfig",
        "params": {"sl_buffer_pct": 0.001, "rr": 2.0},
        "hypothesis": "Sweep + 15m MSS rejection, 0.1% SL buffer, 1:2 R:R",
    },
    {
        "run_id": "run_AsiaSweep_15m_tight_sl",
        "label": "AsiaSweep Tight SL",
        "class_path": "src.gold_research.strategies.session.asia_session_sweep.AsiaSweep",
        "config_class_path": "src.gold_research.strategies.session.asia_session_sweep.AsiaSweepConfig",
        "params": {"sl_buffer_pct": 0.0005, "rr": 2.0},
        "hypothesis": "Tighter SL buffer (0.05%) → fewer noise exits, same 1:2 R:R",
    },
    {
        "run_id": "run_AsiaSweep_15m_wide_rr",
        "label": "AsiaSweep Wide RR",
        "class_path": "src.gold_research.strategies.session.asia_session_sweep.AsiaSweep",
        "config_class_path": "src.gold_research.strategies.session.asia_session_sweep.AsiaSweepConfig",
        "params": {"sl_buffer_pct": 0.001, "rr": 3.0},
        "hypothesis": "Standard SL buffer, wider TP at 1:3 R:R → tests profitability vs win-rate trade-off",
    },
]


# ---------------------------------------------------------------------------
# Engine helpers
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
        max_quantity=Quantity.from_int(1000000),
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


def load_strategy(class_path: str, config_class_path: str):
    import importlib
    mod_path, cls_name = config_class_path.rsplit(".", 1)
    ConfigClass = getattr(importlib.import_module(mod_path), cls_name)
    mod_path, cls_name = class_path.rsplit(".", 1)
    StrategyClass = getattr(importlib.import_module(mod_path), cls_name)
    return StrategyClass, ConfigClass


def build_scorecard(engine: BacktestEngine, run_id: str) -> StrategyScorecard:
    """Extract metrics from a completed BacktestEngine — mirrors Sprint 04 / EMA Cross pattern."""
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
        losers = pnl[pnl <= 0]
        win_rate = len(winners) / total_trades if total_trades > 0 else 0.0
        gross_profit = float(winners.sum()) if len(winners) > 0 else 0.0
        gross_loss = abs(float(losers.sum())) if len(losers) > 0 else 0.0
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )
        net_profit = gross_profit - gross_loss

        equity = pd.Series(100000.0 + pnl.cumsum().values, dtype=float)
        if len(equity) > 1:
            returns = equity.pct_change().dropna()
            sharpe = sharpe_ratio(returns)
            sortino_val = sortino_ratio(returns)
            mdd = max_drawdown(equity)
            calmar_val = calmar_ratio(returns, equity)
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


# ---------------------------------------------------------------------------
# Falsification checks
# ---------------------------------------------------------------------------

def falsification_checks(sc: StrategyScorecard) -> dict:
    checks = {}
    checks["min_trades"]      = {"value": sc.total_trades,          "threshold": ">= 30",   "passed": sc.total_trades >= 30}
    checks["sharpe_positive"] = {"value": round(sc.sharpe, 4),      "threshold": "> 0.5",   "passed": sc.sharpe > 0.5}
    checks["profit_factor"]   = {"value": round(sc.profit_factor,4), "threshold": "> 1.0",  "passed": sc.profit_factor > 1.0}
    checks["max_drawdown"]    = {"value": round(sc.max_dd_pct, 4),  "threshold": "> -0.20", "passed": sc.max_dd_pct > -0.20}
    checks["win_rate_floor"]  = {"value": round(sc.win_rate, 4),    "threshold": "> 0.35",  "passed": sc.win_rate > 0.35}
    all_pass = all(c["passed"] for c in checks.values())
    return {"checks": checks, "verdict": "PASS" if all_pass else "FAIL", "all_pass": all_pass}


# ---------------------------------------------------------------------------
# Single experiment run
# ---------------------------------------------------------------------------

def run_experiment(exp: dict, df_all: pd.DataFrame) -> dict:
    run_id = exp["run_id"]
    logger.info("=" * 60)
    logger.info(f"RUNNING: {exp['label']}  ({run_id})")
    logger.info("=" * 60)

    try:
        bars = df_to_nautilus_bars(df_all.copy(), "XAUUSD", "IDEALPRO", "15m")
        logger.info(f"  Bars converted: {len(bars):,}")

        engine = create_engine()
        add_xauusd_instrument(engine)
        engine.add_data(bars)

        StrategyClass, ConfigClass = load_strategy(exp["class_path"], exp["config_class_path"])
        config = ConfigClass(
            instrument_id="XAUUSD-IDEALPRO-USD",
            timeframe="15m",
            **exp["params"],
        )
        engine.add_strategy(StrategyClass(config=config))

        logger.info("  Engine running…")
        engine.run()
        logger.info("  Engine complete.")

        scorecard = build_scorecard(engine, run_id)
        falsification = falsification_checks(scorecard)

        # Save artifacts
        run_dir = RESULTS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        spec = {
            "experiment_id": "ASIA_SWEEP_15M",
            "run_id": run_id,
            "label": exp["label"],
            "timeframe": "15m",
            "params": exp["params"],
            "data_rows": len(df_all),
            "data_range": f"{df_all['datetime'].min()} -> {df_all['datetime'].max()}",
            "hypothesis": exp["hypothesis"],
        }
        (run_dir / "spec.json").write_text(json.dumps(spec, indent=4, default=str))
        (run_dir / "scorecard.json").write_text(json.dumps(scorecard.model_dump(), indent=4))
        (run_dir / "falsification.json").write_text(json.dumps(falsification, indent=4))

        try:
            pos = engine.trader.generate_positions_report()
            if not pos.empty:
                pos.to_csv(run_dir / "positions.csv")
        except Exception:
            pass
        try:
            fills = engine.trader.generate_order_fills_report()
            if not fills.empty:
                fills.to_csv(run_dir / "fills.csv")
        except Exception:
            pass

        engine.dispose()

        logger.info(
            f"  RESULT: Sharpe={scorecard.sharpe:.4f}, PF={scorecard.profit_factor:.4f}, "
            f"Trades={scorecard.total_trades}, NetPnL=${scorecard.total_net_profit:,.2f}, "
            f"Verdict={falsification['verdict']}"
        )

        return {
            "exp": exp,
            "scorecard": scorecard,
            "falsification": falsification,
            "status": "ok",
            "error": None,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"  FAILED: {type(e).__name__}: {e}")
        return {
            "exp": exp,
            "scorecard": None,
            "falsification": None,
            "status": "error",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _vc(verdict: str) -> str:
    return "pass" if verdict == "PASS" else "fail"


def generate_html_report(outcomes: list, df_meta: dict, elapsed_s: float) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_html = ""
    for o in outcomes:
        exp = o["exp"]
        sc = o["scorecard"]
        fa = o["falsification"]
        if sc is None:
            rows_html += f"""
            <tr>
              <td>{exp['label']}</td>
              <td colspan="9" style="color:var(--accent-red)">ERROR: {o['error']}</td>
              <td><span class="badge badge-fail">ERROR</span></td>
            </tr>"""
            continue

        v = fa["verdict"]
        vc = _vc(v)
        p = exp["params"]
        rows_html += f"""
        <tr>
          <td>{exp['label']}</td>
          <td>buf={p['sl_buffer_pct']*100:.2f}% / RR {p['rr']}</td>
          <td class="num {'pos' if sc.sharpe > 0 else 'neg'}">{sc.sharpe:.4f}</td>
          <td class="num {'pos' if sc.profit_factor > 1 else 'neg'}">{sc.profit_factor:.4f}</td>
          <td class="num">{sc.total_trades}</td>
          <td class="num {'pos' if sc.win_rate > 0.5 else ''}">{sc.win_rate:.1%}</td>
          <td class="num {'pos' if sc.total_net_profit > 0 else 'neg'}">${sc.total_net_profit:,.2f}</td>
          <td class="num neg">{sc.max_dd_pct:.2%}</td>
          <td class="num">{sc.sortino:.4f}</td>
          <td><span class="badge badge-{vc}">{v}</span></td>
        </tr>"""

    checks_html = ""
    for o in outcomes:
        if o["scorecard"] is None:
            continue
        fa = o["falsification"]
        checks_html += f"<h4 style='color:var(--text-secondary);margin:18px 0 8px'>{o['exp']['label']}</h4><div class='checks-grid'>"
        for name, c in fa["checks"].items():
            icon = "✓" if c["passed"] else "✗"
            cls = "check-pass" if c["passed"] else "check-fail"
            checks_html += f"""
            <div class="check-item {cls}">
              <span class="check-icon">{icon}</span>
              <div><strong>{name}</strong><br/>
              <small>{c['value']} (threshold {c['threshold']})</small></div>
            </div>"""
        checks_html += "</div>"

    verdicts_html = "".join(
        f'<div class="verdict-box verdict-{_vc(o["falsification"]["verdict"])}">'
        f'<span class="verdict-icon">{"✅" if o["falsification"]["verdict"] == "PASS" else "❌"}</span>'
        f'<div><strong>{o["exp"]["label"]}</strong> — {o["falsification"]["verdict"]}<br/>'
        f'<span style="font-size:0.9rem;opacity:0.8">{o["exp"]["hypothesis"]}</span></div>'
        f'</div>'
        for o in outcomes if o.get("falsification")
    )

    pass_count = sum(1 for o in outcomes if o.get("falsification") and o["falsification"]["verdict"] == "PASS")
    fail_count = sum(1 for o in outcomes if o.get("falsification") and o["falsification"]["verdict"] == "FAIL")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Asia Session Sweep — XAUUSD 15m Report</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root {{
    --bg-primary: #0a0a0f;
    --bg-secondary: #111118;
    --bg-card: #16161f;
    --bg-elevated: #1e1e2a;
    --text-primary: #e8e8f0;
    --text-secondary: #9898a8;
    --text-muted: #5a5a6e;
    --accent-green: #4ade80;
    --accent-red: #f87171;
    --accent-gold: #fbbf24;
    --accent-blue: #60a5fa;
    --accent-purple: #a78bfa;
    --border: #2a2a38;
}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg-primary);color:var(--text-primary);line-height:1.6;min-height:100vh;}}
.container{{max-width:1400px;margin:0 auto;padding:40px 24px;}}
.hero{{text-align:center;padding:60px 20px;background:linear-gradient(135deg,#0f0f1a 0%,#1a1a2e 50%,#16213e 100%);border-radius:24px;border:1px solid var(--border);margin-bottom:40px;position:relative;overflow:hidden;}}
.hero::before{{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 30% 40%,rgba(251,191,36,0.05) 0%,transparent 50%),radial-gradient(circle at 70% 60%,rgba(74,222,128,0.04) 0%,transparent 50%);animation:pulse 8s ease-in-out infinite alternate;}}
@keyframes pulse{{to{{transform:scale(1.05);}}}}
.hero h1{{font-size:2.8rem;font-weight:900;letter-spacing:-0.03em;margin-bottom:8px;background:linear-gradient(135deg,var(--accent-gold),#f59e0b,var(--accent-green));-webkit-background-clip:text;-webkit-text-fill-color:transparent;position:relative;}}
.hero .subtitle{{font-size:1.05rem;color:var(--text-secondary);position:relative;}}
.hero .meta{{color:var(--text-muted);font-size:0.85rem;margin-top:12px;position:relative;}}
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:40px;}}
.kpi{{background:var(--bg-card);border:1px solid var(--border);border-radius:16px;padding:24px;text-align:center;}}
.kpi-value{{font-size:2rem;font-weight:800;letter-spacing:-0.02em;}}
.kpi-label{{font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em;margin-top:4px;}}
.kpi-green{{color:var(--accent-green);}}
.kpi-red{{color:var(--accent-red);}}
.kpi-gold{{color:var(--accent-gold);}}
.kpi-blue{{color:var(--accent-blue);}}
.kpi-purple{{color:var(--accent-purple);}}
.section{{background:var(--bg-card);border:1px solid var(--border);border-radius:20px;padding:32px;margin-bottom:32px;}}
.section-title{{font-size:1.3rem;font-weight:700;margin-bottom:24px;display:flex;align-items:center;gap:12px;}}
.section-title .icon{{font-size:1.5rem;}}
.pipeline{{display:flex;gap:0;margin-bottom:8px;flex-wrap:wrap;}}
.pipe-step{{background:var(--bg-elevated);border:1px solid var(--border);padding:12px 20px;flex:1;min-width:120px;position:relative;}}
.pipe-step:not(:last-child)::after{{content:"→";position:absolute;right:-12px;top:50%;transform:translateY(-50%);color:var(--accent-gold);font-weight:700;z-index:1;}}
.pipe-step .step-num{{font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;}}
.pipe-step .step-name{{font-size:0.9rem;font-weight:600;color:var(--text-primary);margin-top:2px;}}
.pipe-step .step-detail{{font-size:0.75rem;color:var(--text-secondary);margin-top:2px;}}
.pipe-step.done{{border-color:var(--accent-green);}}
.pipe-step.done .step-num{{color:var(--accent-green);}}
table{{width:100%;border-collapse:collapse;font-size:0.9rem;}}
th{{background:var(--bg-elevated);padding:12px 16px;text-align:left;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);border-bottom:1px solid var(--border);}}
td{{padding:14px 16px;border-bottom:1px solid rgba(42,42,56,0.5);}}
tr:hover td{{background:rgba(30,30,42,0.5);}}
.num{{text-align:right;font-family:monospace;font-size:0.88rem;}}
.pos{{color:var(--accent-green);}}
.neg{{color:var(--accent-red);}}
.badge{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:0.75rem;font-weight:700;letter-spacing:0.05em;}}
.badge-pass{{background:rgba(74,222,128,0.15);color:var(--accent-green);border:1px solid rgba(74,222,128,0.3);}}
.badge-fail{{background:rgba(248,113,113,0.15);color:var(--accent-red);border:1px solid rgba(248,113,113,0.3);}}
.checks-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-bottom:8px;}}
.check-item{{display:flex;align-items:flex-start;gap:12px;background:var(--bg-elevated);border-radius:10px;padding:12px;border:1px solid var(--border);}}
.check-pass{{border-color:rgba(74,222,128,0.3);}}
.check-fail{{border-color:rgba(248,113,113,0.3);}}
.check-icon{{font-size:1.2rem;flex-shrink:0;margin-top:2px;}}
.check-pass .check-icon{{color:var(--accent-green);}}
.check-fail .check-icon{{color:var(--accent-red);}}
.verdict-box{{border-radius:16px;padding:24px 32px;display:flex;align-items:center;gap:20px;font-size:1.05rem;font-weight:600;margin-top:16px;}}
.verdict-fail{{background:rgba(248,113,113,0.08);border:2px solid rgba(248,113,113,0.3);color:var(--accent-red);}}
.verdict-pass{{background:rgba(74,222,128,0.08);border:2px solid rgba(74,222,128,0.3);color:var(--accent-green);}}
.verdict-icon{{font-size:2.5rem;}}
.info-box{{background:var(--bg-elevated);border:1px solid var(--border);border-radius:12px;padding:20px;font-size:0.9rem;color:var(--text-secondary);line-height:1.8;}}
.info-box strong{{color:var(--accent-gold);}}
.next-steps li{{padding:8px 0;border-bottom:1px solid rgba(42,42,56,0.5);color:var(--text-secondary);}}
.next-steps li strong{{color:var(--text-primary);}}
footer{{text-align:center;padding:40px;color:var(--text-muted);font-size:0.8rem;}}
</style>
</head>
<body>
<div class="container">

  <!-- Hero -->
  <div class="hero">
    <h1>Asia Session Sweep — XAUUSD 15m</h1>
    <p class="subtitle">Sweep + Market Structure Shift (MSS) reversal &bull; Real IBKR data &bull; Full dataset</p>
    <p class="meta">Generated {now_str} &bull; Elapsed {elapsed_s:.1f}s &bull; Gold Research Factory &bull; Solid2026</p>
  </div>

  <!-- KPI strip -->
  <div class="kpi-strip">
    <div class="kpi">
      <div class="kpi-value kpi-gold">{df_meta['bars']:,}</div>
      <div class="kpi-label">15m Bars (full)</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-blue">{len(outcomes)}</div>
      <div class="kpi-label">Configs Tested</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-green">{pass_count}</div>
      <div class="kpi-label">PASS</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-red">{fail_count}</div>
      <div class="kpi-label">FAIL</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-purple">{df_meta['start']}</div>
      <div class="kpi-label">Data Start</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-purple">{df_meta['end']}</div>
      <div class="kpi-label">Data End</div>
    </div>
  </div>

  <!-- Strategy overview -->
  <div class="section">
    <div class="section-title"><span class="icon">🎯</span> Strategy Overview</div>
    <div class="info-box">
      <strong>Asia Session Sweep</strong> — Novel (no prior implementation in Solid2026 registry).<br/>
      <strong>Concept:</strong> Mark the pre-Asia swing high/low from 15m bars in the 21:00–00:59 UTC window
      (NY after-hours / pre-Asia consolidation). During the Asia entry window (01:00–04:59 UTC), wait for price
      to sweep one of these levels — a 15m bar whose wick extends past the marked level but whose <em>close
      returns inside the range</em> (Market Structure Shift approximation). Enter on that bar's close at 1:2 R:R.<br/>
      <strong>SL:</strong> Above sweep wick high (shorts) / below sweep wick low (longs) + buffer.<br/>
      <strong>Invalidation:</strong> Close fully outside range, or no setup by 05:00 UTC.<br/>
      <strong>Data limitation:</strong> Original spec uses M1 for MSS; approximated here on 15m (smallest available).
    </div>
  </div>

  <!-- Pipeline -->
  <div class="section">
    <div class="section-title"><span class="icon">⚙️</span> Backtesting Flow</div>
    <div class="pipeline">
      <div class="pipe-step done">
        <div class="step-num">Stage 1</div>
        <div class="step-name">Data Load</div>
        <div class="step-detail">xauusd_15_mins.parquet (full)</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 2</div>
        <div class="step-name">Nautilus Bars</div>
        <div class="step-detail">df_to_nautilus_bars(15m)</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 3</div>
        <div class="step-name">Engine Setup</div>
        <div class="step-detail">IDEALPRO / MARGIN / $100k</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 4</div>
        <div class="step-name">Session State</div>
        <div class="step-detail">Range (21–01 UTC) + Entry (01–05 UTC)</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 5</div>
        <div class="step-name">Sweep + MSS</div>
        <div class="step-detail">Wick past level, close inside</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 6</div>
        <div class="step-name">Fixed R:R Exit</div>
        <div class="step-detail">TP/SL on bar high/low</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 7</div>
        <div class="step-name">Scorecard</div>
        <div class="step-detail">Sharpe / PF / MDD / Win Rate</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 8</div>
        <div class="step-name">Falsification</div>
        <div class="step-detail">5 hard gates applied</div>
      </div>
    </div>
  </div>

  <!-- Results table -->
  <div class="section">
    <div class="section-title"><span class="icon">📊</span> Strategy Results — Real IBKR 15m Data (Full Dataset)</div>
    <table>
      <thead>
        <tr>
          <th>Strategy</th>
          <th>Params</th>
          <th style="text-align:right">Sharpe</th>
          <th style="text-align:right">Profit Factor</th>
          <th style="text-align:right">Trades</th>
          <th style="text-align:right">Win Rate</th>
          <th style="text-align:right">Net P&amp;L</th>
          <th style="text-align:right">Max DD</th>
          <th style="text-align:right">Sortino</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <!-- Falsification -->
  <div class="section">
    <div class="section-title"><span class="icon">🔬</span> Falsification Checks (per configuration)</div>
    <p style="color:var(--text-secondary);margin-bottom:16px;font-size:0.9rem;">
      All 5 gates must pass for PASS verdict. Thresholds match Sprint 04 real-data standard.
    </p>
    {checks_html}
  </div>

  <!-- Verdicts -->
  <div class="section">
    <div class="section-title"><span class="icon">⚖️</span> Verdicts</div>
    {verdicts_html}
    <div class="info-box" style="margin-top:24px;">
      <strong>Duplicate check:</strong> NOVEL — no prior implementation of session sweep, MSS, order block,
      FVG, or breaker logic exists in the Solid2026 registry. Closest neighbour is
      OpeningRangeBreakout (ORB), which is a morning-range breakout continuation strategy — structurally
      opposite to Asia Sweep's reversal after stop-hunt mechanism.<br/><br/>
      <strong>Prior findings context:</strong> XAUUSD 15m is strongly mean-reverting (BollReversion Sharpe 6.74,
      ZScore Sharpe 5.03). The Asia Sweep is a session-specific reversal strategy — architecturally compatible
      with mean-reversion tendencies but anchored to institutional liquidity hunt timing. This is the first
      session-scoped strategy in the portfolio.
    </div>
  </div>

  <!-- Next steps -->
  <div class="section">
    <div class="section-title"><span class="icon">🗺️</span> Next Steps</div>
    <ul class="next-steps" style="list-style:none;padding:0;">
      <li><strong>If any config PASSed:</strong> Run 3-fold walk-forward (WFE ≥ 40%), cost-stress at 3× spread,
        and correlation check against GOLD_PORT_02 (BollReversion + ZScoreReversion + SqueezeBreakout).</li>
      <li><strong>If all FAILed — too few trades:</strong> Check actual trade count; if &lt; 30, the 15m sweep
        pattern is too rare. Consider relaxing the MSS filter: accept any close-below-swept-high bar (not just
        wick+close-inside on same bar).</li>
      <li><strong>If all FAILed — poor Sharpe:</strong> The session timing approximation (15m vs M1) loses
        precision. Options: acquire 1m or 5m data, or add an ADX/volatility regime filter
        (only trade when pre-Asia range ≥ 1× ATR).</li>
      <li><strong>Parameter extension:</strong> Test different entry windows (01–03 UTC vs 01–05 UTC),
        minimum range width gates, and partial TP at 1:1 with BE move.</li>
      <li><strong>Rejection path:</strong> If strategy fails all configs, document in
        <code>journal/rejected_ideas.md</code> with root cause (insufficient M1 data, rare setup, etc.).</li>
    </ul>
  </div>

  <footer>
    Gold Research Factory &bull; Solid2026 &bull; Falsification-First Research &bull;
    Script: scripts/run_asia_sweep_15m.py &bull; Strategy: src/gold_research/strategies/session/asia_session_sweep.py
  </footer>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 70)
    logger.info("ASIA SESSION SWEEP — XAUUSD 15m — FULL DATASET")
    logger.info("=" * 70)

    t0 = datetime.now()

    # 1. Load all 15m data
    logger.info(f"Loading 15m data from {RAW_15M.name}…")
    df = load_ib_parquet(str(RAW_15M))
    df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
    logger.info(f"Full dataset: {len(df):,} bars  [{df['datetime'].min()} → {df['datetime'].max()}]")

    if len(df) < 100:
        logger.error("Insufficient data. Aborting.")
        sys.exit(1)

    df_meta = {
        "bars": len(df),
        "start": str(df["datetime"].min().date()),
        "end":   str(df["datetime"].max().date()),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Run all experiments
    outcomes = []
    for exp in EXPERIMENTS:
        result = run_experiment(exp, df)
        outcomes.append(result)

    elapsed = (datetime.now() - t0).total_seconds()

    # 3. Summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info(f"{'Strategy':<30} {'Sharpe':>8} {'PF':>8} {'Trades':>8} {'NetPnL':>12} {'Verdict':>8}")
    logger.info("-" * 70)
    for o in outcomes:
        sc = o["scorecard"]
        fa = o["falsification"]
        label = o["exp"]["label"]
        if sc:
            logger.info(
                f"{label:<30} {sc.sharpe:>8.4f} {sc.profit_factor:>8.4f} "
                f"{sc.total_trades:>8} ${sc.total_net_profit:>10,.2f} {fa['verdict']:>8}"
            )
        else:
            logger.info(f"{label:<30} {'ERROR':>8}")

    # 4. Experiment log
    log_path = RESULTS_DIR / "experiment_log.json"
    log_data = {
        "experiment": "ASIA_SWEEP_15M",
        "run_at": t0.isoformat(),
        "elapsed_s": round(elapsed, 2),
        "data_meta": df_meta,
        "results": [
            {
                "run_id": o["exp"]["run_id"],
                "label": o["exp"]["label"],
                "params": o["exp"]["params"],
                "status": o["status"],
                "error": o["error"],
                "scorecard": o["scorecard"].model_dump() if o["scorecard"] else None,
                "falsification": o["falsification"],
            }
            for o in outcomes
        ],
    }
    log_path.write_text(json.dumps(log_data, indent=4, default=str))
    logger.info(f"\nExperiment log: {log_path}")

    # 5. HTML report
    html = generate_html_report(outcomes, df_meta, elapsed)
    REPORT_PATH.write_text(html, encoding="utf-8")
    logger.info(f"HTML report:    {REPORT_PATH}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
