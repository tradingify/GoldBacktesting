"""
EMA/MA Cross Experiment — XAUUSD 15m, Last 6 Months
=====================================================
Runs both the EMA cross (EMACross) and SMA cross (MovingAverageCross) strategies
against the last 6 months of real IBKR 15m data, applies the standard
falsification checklist, saves artifacts, and generates an HTML report.

Parameters tested:
  EMACross   fast=9,  slow=21   (classic 9/21 EMA)
  EMACross   fast=20, slow=50   (matches sprint-02 SMA params for apples-to-apples)
  MACross    fast=20, slow=50   (baseline SMA, frozen sprint-02 params)

Falsification gates (same thresholds as Sprint 04):
  PASS  → Sharpe > 0.5  AND  Profit Factor > 1.0
  FAIL  → otherwise

Usage:
  $env:PYTHONPATH = "D:\\.openclaw\\GoldBacktesting\\Solid2026"
  python scripts/run_ema_cross_15m.py
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
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
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("ema_cross_15m")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_15M = Path(r"D:\.openclaw\GoldBacktesting\bars\xauusd_15_mins.parquet")
RESULTS_DIR = ProjectPaths.RESULTS / "raw_runs" / "EMA_CROSS_15M"
REPORT_PATH = RESULTS_DIR / "ema_cross_15m_report.html"

# ---------------------------------------------------------------------------
# Experiment definitions
# ---------------------------------------------------------------------------
EXPERIMENTS = [
    {
        "run_id": "run_EMACross_15m_9_21",
        "label": "EMACross 9/21",
        "class_path": "src.gold_research.strategies.trend.ema_cross.EMACross",
        "config_class_path": "src.gold_research.strategies.trend.ema_cross.EMACrossConfig",
        "params": {"fast_period": 9, "slow_period": 21, "trail_atr_multiplier": 2.0},
        "hypothesis": "Fast EMA(9) / Slow EMA(21) classic intraday cross",
    },
    {
        "run_id": "run_EMACross_15m_20_50",
        "label": "EMACross 20/50",
        "class_path": "src.gold_research.strategies.trend.ema_cross.EMACross",
        "config_class_path": "src.gold_research.strategies.trend.ema_cross.EMACrossConfig",
        "params": {"fast_period": 20, "slow_period": 50, "trail_atr_multiplier": 2.0},
        "hypothesis": "EMA(20)/EMA(50) — apples-to-apples with Sprint-02 SMA params",
    },
    {
        "run_id": "run_MACross_15m_20_50",
        "label": "MACross 20/50 (SMA baseline)",
        "class_path": "src.gold_research.strategies.trend.moving_average_cross.MovingAverageCross",
        "config_class_path": "src.gold_research.strategies.trend.moving_average_cross.MACrossConfig",
        "params": {"fast_period": 20, "slow_period": 50, "trail_atr_multiplier": 2.0},
        "hypothesis": "Frozen Sprint-02 SMA cross on 15m (baseline comparison)",
    },
]


# ---------------------------------------------------------------------------
# Engine helpers  (identical pattern to run_sprint04.py)
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
    """Extract metrics from a completed BacktestEngine — mirrors Sprint 04 logic."""
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
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
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
    checks["min_trades"]       = {"value": sc.total_trades,     "threshold": ">= 30",  "passed": sc.total_trades >= 30}
    checks["sharpe_positive"]  = {"value": round(sc.sharpe, 4), "threshold": "> 0.5",  "passed": sc.sharpe > 0.5}
    checks["profit_factor"]    = {"value": round(sc.profit_factor, 4), "threshold": "> 1.0", "passed": sc.profit_factor > 1.0}
    checks["max_drawdown"]     = {"value": round(sc.max_dd_pct, 4), "threshold": "> -0.20", "passed": sc.max_dd_pct > -0.20}
    checks["win_rate_floor"]   = {"value": round(sc.win_rate, 4),   "threshold": "> 0.35", "passed": sc.win_rate > 0.35}
    all_pass = all(c["passed"] for c in checks.values())
    verdict = "PASS" if all_pass else "FAIL"
    return {"checks": checks, "verdict": verdict, "all_pass": all_pass}


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------
def run_experiment(exp: dict, df_6mo: pd.DataFrame) -> dict:
    run_id = exp["run_id"]
    logger.info(f"{'='*60}")
    logger.info(f"RUNNING: {exp['label']}  ({run_id})")
    logger.info(f"{'='*60}")

    try:
        bars = df_to_nautilus_bars(df_6mo.copy(), "XAUUSD", "IDEALPRO", "15m")
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

        # Save run directory
        run_dir = RESULTS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        spec = {
            "experiment_id": "EMA_CROSS_15M",
            "run_id": run_id,
            "label": exp["label"],
            "timeframe": "15m",
            "params": exp["params"],
            "data_rows": len(df_6mo),
            "data_range": f"{df_6mo['datetime'].min()} -> {df_6mo['datetime'].max()}",
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
# HTML report generator
# ---------------------------------------------------------------------------
def _verdict_class(v: str) -> str:
    return "pass" if v == "PASS" else "fail"


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
              <td colspan="8" style="color:var(--accent-red)">ERROR: {o['error']}</td>
              <td><span class="badge badge-fail">ERROR</span></td>
            </tr>"""
            continue

        v = fa["verdict"]
        vc = _verdict_class(v)
        rows_html += f"""
        <tr>
          <td>{exp['label']}</td>
          <td>{exp['params']['fast_period']}/{exp['params']['slow_period']}</td>
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

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EMA/MA Cross 15m — XAUUSD Experiment Report</title>
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
    --glow-green: 0 0 20px rgba(74,222,128,0.15);
    --glow-red: 0 0 20px rgba(248,113,113,0.15);
}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg-primary);color:var(--text-primary);line-height:1.6;min-height:100vh;}}
.container{{max-width:1400px;margin:0 auto;padding:40px 24px;}}
.hero{{text-align:center;padding:60px 20px;background:linear-gradient(135deg,#0f0f1a 0%,#1a1a2e 50%,#16213e 100%);border-radius:24px;border:1px solid var(--border);margin-bottom:40px;position:relative;overflow:hidden;}}
.hero::before{{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 30% 40%,rgba(251,191,36,0.05) 0%,transparent 50%),radial-gradient(circle at 70% 60%,rgba(74,222,128,0.04) 0%,transparent 50%);animation:pulse 8s ease-in-out infinite alternate;}}
@keyframes pulse{{to{{transform:scale(1.05);}}}}
.hero h1{{font-size:3rem;font-weight:900;letter-spacing:-0.03em;margin-bottom:8px;background:linear-gradient(135deg,var(--accent-gold),#f59e0b,var(--accent-green));-webkit-background-clip:text;-webkit-text-fill-color:transparent;position:relative;}}
.hero .subtitle{{font-size:1.1rem;color:var(--text-secondary);position:relative;}}
.hero .meta{{color:var(--text-muted);font-size:0.85rem;margin-top:12px;position:relative;}}
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:40px;}}
.kpi{{background:var(--bg-card);border:1px solid var(--border);border-radius:16px;padding:24px;text-align:center;transition:transform 0.2s,box-shadow 0.2s;}}
.kpi:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,0.3);}}
.kpi-value{{font-size:2.2rem;font-weight:800;letter-spacing:-0.02em;}}
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
.verdict-box{{border-radius:16px;padding:24px 32px;display:flex;align-items:center;gap:20px;font-size:1.1rem;font-weight:600;margin-top:16px;}}
.verdict-fail{{background:rgba(248,113,113,0.08);border:2px solid rgba(248,113,113,0.3);color:var(--accent-red);}}
.verdict-pass{{background:rgba(74,222,128,0.08);border:2px solid rgba(74,222,128,0.3);color:var(--accent-green);}}
.verdict-icon{{font-size:2.5rem;}}
.next-steps li{{padding:8px 0;border-bottom:1px solid rgba(42,42,56,0.5);color:var(--text-secondary);}}
.next-steps li strong{{color:var(--text-primary);}}
.tag{{display:inline-block;background:rgba(251,191,36,0.1);color:var(--accent-gold);border:1px solid rgba(251,191,36,0.2);border-radius:8px;padding:2px 10px;font-size:0.75rem;margin-right:6px;}}
footer{{text-align:center;padding:40px;color:var(--text-muted);font-size:0.8rem;}}
</style>
</head>
<body>
<div class="container">

  <!-- Hero -->
  <div class="hero">
    <h1>EMA / MA Cross — XAUUSD 15m</h1>
    <p class="subtitle">Framework-native EMA crossover experiment &bull; Real IBKR data &bull; Last 6 months</p>
    <p class="meta">Generated {now_str} &bull; Elapsed {elapsed_s:.1f}s &bull; Gold Research Factory &bull; Solid2026</p>
  </div>

  <!-- KPI strip -->
  <div class="kpi-strip">
    <div class="kpi">
      <div class="kpi-value kpi-gold">{df_meta['bars']:,}</div>
      <div class="kpi-label">15m Bars (6 mo)</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-blue">{len(outcomes)}</div>
      <div class="kpi-label">Configurations Tested</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-green">{sum(1 for o in outcomes if o.get('falsification') and o['falsification']['verdict']=='PASS')}</div>
      <div class="kpi-label">PASS</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-red">{sum(1 for o in outcomes if o.get('falsification') and o['falsification']['verdict']=='FAIL')}</div>
      <div class="kpi-label">FAIL</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-purple">{df_meta['start']}</div>
      <div class="kpi-label">Data Start (UTC)</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-purple">{df_meta['end']}</div>
      <div class="kpi-label">Data End (UTC)</div>
    </div>
  </div>

  <!-- Flow pipeline -->
  <div class="section">
    <div class="section-title"><span class="icon">⚙️</span> Backtesting Flow — Stages Executed</div>
    <div class="pipeline">
      <div class="pipe-step done">
        <div class="step-num">Stage 1</div>
        <div class="step-name">Data Load</div>
        <div class="step-detail">load_ib_parquet(xauusd_15_mins.parquet)</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 2</div>
        <div class="step-name">6-Month Filter</div>
        <div class="step-detail">datetime ≥ now() − 183 days</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 3</div>
        <div class="step-name">Nautilus Bars</div>
        <div class="step-detail">df_to_nautilus_bars(15m)</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 4</div>
        <div class="step-name">Engine Setup</div>
        <div class="step-detail">IDEALPRO / MARGIN / $100k</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 5</div>
        <div class="step-name">Strategy Init</div>
        <div class="step-detail">EMACross / MACross (3 configs)</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 6</div>
        <div class="step-name">Engine.run()</div>
        <div class="step-detail">BacktestEngine full replay</div>
      </div>
      <div class="pipe-step done">
        <div class="step-num">Stage 7</div>
        <div class="step-name">Scorecard</div>
        <div class="step-detail">build_scorecard_from_engine()</div>
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
    <div class="section-title"><span class="icon">📊</span> Strategy Results — Real IBKR 15m Data</div>
    <table>
      <thead>
        <tr>
          <th>Strategy</th>
          <th>Fast/Slow</th>
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

  <!-- Falsification checks -->
  <div class="section">
    <div class="section-title"><span class="icon">🔬</span> Falsification Checks (per configuration)</div>
    <p style="color:var(--text-secondary);margin-bottom:16px;font-size:0.9rem;">
      Each strategy must pass all 5 hard gates to receive a PASS verdict. Thresholds match Sprint 04 real-data validation.
    </p>
    {checks_html}
  </div>

  <!-- Verdicts -->
  <div class="section">
    <div class="section-title"><span class="icon">⚖️</span> Overall Verdicts &amp; Context</div>

    {"".join(
        f'<div class="verdict-box verdict-{_verdict_class(o["falsification"]["verdict"])}">'
        f'<span class="verdict-icon">{"✅" if o["falsification"]["verdict"] == "PASS" else "❌"}</span>'
        f'<div><strong>{o["exp"]["label"]}</strong> — {o["falsification"]["verdict"]}<br/>'
        f'<span style="font-size:0.9rem;opacity:0.8">{o["exp"]["hypothesis"]}</span></div>'
        f'</div>'
        for o in outcomes if o.get("falsification")
    )}

    <div style="margin-top:24px;padding:20px;background:var(--bg-elevated);border-radius:12px;border:1px solid var(--border);">
      <p style="font-size:0.95rem;color:var(--text-secondary);line-height:1.8;">
        <strong style="color:var(--accent-gold)">Context from Sprint 02 &amp; 04:</strong>
        SMA-based MA Cross was tested across all timeframes (5m / 15m / 1h / 4h) on synthetic data in Sprint 02.
        The 1h variant achieved Sharpe 1.19 but was <em>rejected due to cost-stress failure</em> (harsh PF = 0.48).
        The 4h variant achieved Sharpe 1.12 but <em>failed walk-forward</em> (avg WFE = 0.29, below 40% threshold).
        No 15m MACross variant survived Sprint 02 robustness. EMA cross reacts faster to price changes and may
        produce more trades on 15m but faces the same fundamental challenge: XAUUSD 15m is dominated by
        mean-reverting behavior (as evidenced by BollReversion Sharpe 6.74 and ZScoreReversion Sharpe 5.03 on real data).
        Trend-following cross systems consistently underperform in this regime.
      </p>
    </div>
  </div>

  <!-- Next steps -->
  <div class="section">
    <div class="section-title"><span class="icon">🗺️</span> Next Steps</div>
    <ul class="next-steps" style="list-style:none;padding:0;">
      <li><strong>If any variant PASSed:</strong> proceed to 3-fold walk-forward validation (WFE ≥ 40% gate), cost-stress testing (harsh spread 3×), and regime segmentation before considering portfolio inclusion.</li>
      <li><strong>If all variants FAILed (expected):</strong> document in <code>journal/rejected_ideas.md</code>. Consider testing EMA cross on higher timeframes (1h/4h) where trend signals have more follow-through, or filtering entries with a regime filter (ADX > 25).</li>
      <li><strong>EMA vs SMA comparison:</strong> if EMA cross produces materially better Sharpe than SMA cross on this timeframe, log the finding and add an ADX-filtered variant to the hypothesis backlog.</li>
      <li><strong>Portfolio diversification:</strong> a weak/marginal EMA cross could still add value as a portfolio component if correlation with BollReversion + ZScoreReversion is low (target ρ &lt; 0.3).</li>
      <li><strong>Parameter sensitivity:</strong> test 5/13, 12/26, 20/50, 50/200 EMA pairs on 15m to map the parameter landscape rather than cherry-pick a single point.</li>
    </ul>
  </div>

  <footer>
    Gold Research Factory &bull; Solid2026 &bull; Falsification-First Research &bull;
    Script: scripts/run_ema_cross_15m.py &bull; Strategy: src/gold_research/strategies/trend/ema_cross.py
  </footer>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    logger.info("=" * 70)
    logger.info("EMA/MA CROSS EXPERIMENT — XAUUSD 15m — LAST 6 MONTHS")
    logger.info("=" * 70)

    t0 = datetime.now()

    # 1. Load 15m data
    logger.info(f"Loading 15m data from {RAW_15M.name}…")
    df = load_ib_parquet(str(RAW_15M))
    df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
    logger.info(f"Full dataset: {len(df):,} bars  [{df['datetime'].min()} → {df['datetime'].max()}]")

    # 2. Filter to last 6 months
    cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=183)
    df_6mo = df[df["datetime"] >= cutoff].reset_index(drop=True)
    logger.info(f"6-month window (>= {cutoff.date()}): {len(df_6mo):,} bars  "
                f"[{df_6mo['datetime'].min()} → {df_6mo['datetime'].max()}]")

    if len(df_6mo) < 100:
        logger.error("Insufficient data for the 6-month window. Aborting.")
        sys.exit(1)

    df_meta = {
        "bars": len(df_6mo),
        "start": str(df_6mo["datetime"].min().date()),
        "end":   str(df_6mo["datetime"].max().date()),
    }

    # 3. Create results dir
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 4. Run all experiments
    outcomes = []
    for exp in EXPERIMENTS:
        result = run_experiment(exp, df_6mo)
        outcomes.append(result)

    elapsed = (datetime.now() - t0).total_seconds()

    # 5. Summary table
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info(f"{'Strategy':<28} {'Sharpe':>8} {'PF':>8} {'Trades':>8} {'NetPnL':>12} {'Verdict':>8}")
    logger.info("-" * 70)
    for o in outcomes:
        sc = o["scorecard"]
        fa = o["falsification"]
        label = o["exp"]["label"]
        if sc:
            logger.info(f"{label:<28} {sc.sharpe:>8.4f} {sc.profit_factor:>8.4f} "
                        f"{sc.total_trades:>8} ${sc.total_net_profit:>10,.2f} {fa['verdict']:>8}")
        else:
            logger.info(f"{label:<28} {'ERROR':>8}")

    # 6. Save experiment log
    log_path = RESULTS_DIR / "experiment_log.json"
    log_data = {
        "experiment": "EMA_CROSS_15M",
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

    # 7. Generate HTML report
    html = generate_html_report(outcomes, df_meta, elapsed)
    REPORT_PATH.write_text(html, encoding="utf-8")
    logger.info(f"HTML report:    {REPORT_PATH}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
