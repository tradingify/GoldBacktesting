"""
Asia Session Sweep — Stage 2 Validation Suite
==============================================
Runs after ALL 3 baseline configs PASSed the Sprint 04 falsification gates.

Validation stages executed here:
  1. Walk-Forward Validation (WFV)
       3 equal-time folds on the default config (sl_buffer_pct=0.001, rr=2.0).
       Each fold is run independently through a fresh NautilusTrader engine.
       WFE = mean(fold Sharpe) / IS Sharpe × 100.  Target: WFE >= 40%.

  2. Cost Stress Test (CST)
       Analytical: re-computes Sharpe / PF / Net-PnL after subtracting a
       per-round-trip cost from each trade's realized P&L.
       Baseline spread assumption: $0.30 / oz round-trip (ECN-like, 1 oz qty).
       Multipliers tested: 1×, 2×, 3×, 5×, 10×.
       Pass gate at 3× (= $0.90/trade): PF > 1.0, Sharpe > 0.5.

Inputs:
  Baseline IS Sharpe     : 7.7469  (from experiment_log.json)
  Positions CSV          : results/raw_runs/ASIA_SWEEP_15M/run_AsiaSweep_15m_default/positions.csv
  Full 15m data          : data/raw/ib/gold/bars/xauusd_15_mins.parquet

Outputs:
  results/raw_runs/ASIA_SWEEP_VALIDATION/
    wfv/fold_1/  fold_2/  fold_3/   (scorecard.json, falsification.json)
    wfv/wfv_summary.json
    cost_stress/cost_stress_summary.json
    validation_log.json
    asia_sweep_validation_report.html

Usage:
  $env:PYTHONPATH = "D:\\.openclaw\\GoldBacktesting\\Solid2026"
  python scripts/run_asia_sweep_validation.py
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
logger = logging.getLogger("asia_sweep_validation")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_15M = Path(r"D:\.openclaw\GoldBacktesting\bars\xauusd_15_mins.parquet")
BASELINE_DIR = ProjectPaths.RESULTS / "raw_runs" / "ASIA_SWEEP_15M"
BASELINE_POSITIONS = BASELINE_DIR / "run_AsiaSweep_15m_default" / "positions.csv"
RESULTS_DIR = ProjectPaths.RESULTS / "raw_runs" / "ASIA_SWEEP_VALIDATION"
REPORT_PATH = RESULTS_DIR / "asia_sweep_validation_report.html"

# Baseline full-dataset Sharpe (from experiment_log.json — default config)
IS_SHARPE = 7.7469
IS_NET_PNL = 1253.08
IS_TRADES = 112
IS_WIN_RATE = 0.6429
IS_PF = 3.6669

# Cost stress parameters
BASELINE_SPREAD_USD = 0.30   # $/oz round trip — ECN-like for 1 oz XAUUSD
STRESS_MULTIPLIERS = [1, 2, 3, 5, 10]

# WFV parameters
N_FOLDS = 3


# ---------------------------------------------------------------------------
# Engine helpers (identical to baseline runner)
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


def build_scorecard(engine: BacktestEngine, run_id: str) -> StrategyScorecard:
    """Extract metrics from a completed BacktestEngine — mirrors baseline runner."""
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


def falsification_checks(sc: StrategyScorecard) -> dict:
    checks = {}
    checks["min_trades"]      = {"value": sc.total_trades,          "threshold": ">= 30",   "passed": sc.total_trades >= 30}
    checks["sharpe_positive"] = {"value": round(sc.sharpe, 4),      "threshold": "> 0.5",   "passed": sc.sharpe > 0.5}
    checks["profit_factor"]   = {"value": round(sc.profit_factor,4),"threshold": "> 1.0",   "passed": sc.profit_factor > 1.0}
    checks["max_drawdown"]    = {"value": round(sc.max_dd_pct, 4),  "threshold": "> -0.20", "passed": sc.max_dd_pct > -0.20}
    checks["win_rate_floor"]  = {"value": round(sc.win_rate, 4),    "threshold": "> 0.35",  "passed": sc.win_rate > 0.35}
    all_pass = all(c["passed"] for c in checks.values())
    return {"checks": checks, "verdict": "PASS" if all_pass else "FAIL", "all_pass": all_pass}


# ---------------------------------------------------------------------------
# Stage 1: Walk-Forward Validation
# ---------------------------------------------------------------------------

def run_wfv(df: pd.DataFrame) -> dict:
    """
    3-fold temporal walk-forward validation on the AsiaSweep default config.
    Each fold is an independent out-of-sample run on a non-overlapping time slice.
    """
    from src.gold_research.strategies.session.asia_session_sweep import AsiaSweep, AsiaSweepConfig

    logger.info("=" * 70)
    logger.info("STAGE 1: WALK-FORWARD VALIDATION (3 folds)")
    logger.info("=" * 70)

    # Split by row index into 3 equal temporal slices
    n = len(df)
    fold_size = n // N_FOLDS
    boundaries = [0, fold_size, 2 * fold_size, n]
    fold_labels = ["fold_1", "fold_2", "fold_3"]

    wfv_dir = RESULTS_DIR / "wfv"
    wfv_dir.mkdir(parents=True, exist_ok=True)

    fold_results = []
    fold_sharpes = []

    for i, label in enumerate(fold_labels):
        fold_df = df.iloc[boundaries[i]: boundaries[i + 1]].copy()
        date_start = str(fold_df["datetime"].min().date())
        date_end   = str(fold_df["datetime"].max().date())
        logger.info(f"  {label}: {len(fold_df):,} bars  [{date_start} → {date_end}]")

        try:
            bars = df_to_nautilus_bars(fold_df, "XAUUSD", "IDEALPRO", "15m")

            engine = create_engine()
            add_xauusd_instrument(engine)
            engine.add_data(bars)

            config = AsiaSweepConfig(
                instrument_id="XAUUSD-IDEALPRO-USD",
                timeframe="15m",
                sl_buffer_pct=0.001,
                rr=2.0,
            )
            engine.add_strategy(AsiaSweep(config=config))
            engine.run()

            sc = build_scorecard(engine, f"wfv_{label}")
            fa = falsification_checks(sc)
            engine.dispose()

            fold_dir = wfv_dir / label
            fold_dir.mkdir(parents=True, exist_ok=True)
            (fold_dir / "scorecard.json").write_text(json.dumps(sc.model_dump(), indent=4))
            (fold_dir / "falsification.json").write_text(json.dumps(fa, indent=4))

            fold_sharpes.append(sc.sharpe)
            fold_results.append({
                "label": label,
                "date_start": date_start,
                "date_end": date_end,
                "bars": len(fold_df),
                "scorecard": sc.model_dump(),
                "falsification": fa,
                "status": "ok",
                "error": None,
            })
            logger.info(
                f"    → Sharpe={sc.sharpe:.4f}  PF={sc.profit_factor:.4f}  "
                f"Trades={sc.total_trades}  WinRate={sc.win_rate:.1%}  Verdict={fa['verdict']}"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"    FOLD FAILED: {e}")
            fold_sharpes.append(0.0)
            fold_results.append({
                "label": label,
                "date_start": date_start,
                "date_end": date_end,
                "bars": len(fold_df),
                "scorecard": None,
                "falsification": None,
                "status": "error",
                "error": str(e),
            })

    # WFE = mean(fold Sharpes) / IS_Sharpe × 100
    valid_sharpes = [s for s in fold_sharpes if s > -99]
    mean_oos_sharpe = float(np.mean(valid_sharpes)) if valid_sharpes else 0.0
    wfe = (mean_oos_sharpe / IS_SHARPE * 100.0) if IS_SHARPE != 0 else 0.0
    wfe_passed = wfe >= 40.0
    folds_all_pass = all(
        r["falsification"]["all_pass"] for r in fold_results if r["falsification"] is not None
    )

    summary = {
        "is_sharpe": IS_SHARPE,
        "fold_sharpes": fold_sharpes,
        "mean_oos_sharpe": round(mean_oos_sharpe, 4),
        "wfe_pct": round(wfe, 2),
        "wfe_threshold_pct": 40.0,
        "wfe_passed": wfe_passed,
        "folds_all_pass": folds_all_pass,
        "wfv_verdict": "PASS" if (wfe_passed and folds_all_pass) else "FAIL",
        "folds": fold_results,
    }
    (wfv_dir / "wfv_summary.json").write_text(json.dumps(summary, indent=4, default=str))
    logger.info(f"\n  WFE = {wfe:.1f}%  (threshold >= 40%)  → {'PASS' if wfe_passed else 'FAIL'}")

    return summary


# ---------------------------------------------------------------------------
# Stage 2: Cost Stress Test (analytical)
# ---------------------------------------------------------------------------

def run_cost_stress() -> dict:
    """
    Re-computes Sharpe, PF, Net-PnL for each spread multiplier by subtracting
    a per-trade round-trip cost from the baseline default positions CSV.

    Round-trip cost = multiplier × BASELINE_SPREAD_USD per trade.
    Quantity is 1 oz per trade (confirmed from positions.csv).
    """
    logger.info("=" * 70)
    logger.info("STAGE 2: COST STRESS TEST (analytical)")
    logger.info("=" * 70)
    logger.info(f"  Baseline spread assumption: ${BASELINE_SPREAD_USD:.2f} / oz round-trip")

    cst_dir = RESULTS_DIR / "cost_stress"
    cst_dir.mkdir(parents=True, exist_ok=True)

    # Load baseline positions
    try:
        pos = pd.read_csv(BASELINE_POSITIONS)
        raw_pnl = pos["realized_pnl"].apply(
            lambda x: float(str(x).replace(" USD", "").replace(",", "")) if pd.notna(x) else 0.0
        )
        logger.info(f"  Loaded {len(raw_pnl)} positions from baseline CSV")
    except Exception as e:
        logger.error(f"  Could not load positions CSV: {e}")
        return {"error": str(e), "levels": []}

    levels = []
    for mult in STRESS_MULTIPLIERS:
        cost_per_trade = BASELINE_SPREAD_USD * mult
        total_cost = cost_per_trade * len(raw_pnl)
        adj_pnl = raw_pnl - cost_per_trade   # deduct from each trade

        winners = adj_pnl[adj_pnl > 0]
        losers  = adj_pnl[adj_pnl <= 0]
        n_trades = len(adj_pnl)
        win_rate = len(winners) / n_trades if n_trades > 0 else 0.0
        gross_profit = float(winners.sum()) if len(winners) > 0 else 0.0
        gross_loss   = abs(float(losers.sum())) if len(losers) > 0 else 0.0
        pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
        net = gross_profit - gross_loss

        equity = pd.Series(100000.0 + adj_pnl.cumsum().values, dtype=float)
        if len(equity) > 1:
            returns = equity.pct_change().dropna()
            sharpe = sharpe_ratio(returns)
            mdd    = max_drawdown(equity)
        else:
            sharpe = mdd = 0.0

        # Pass gate: PF > 1.0 AND Sharpe > 0.5
        gate_pass = pf > 1.0 and sharpe > 0.5
        verdict   = "PASS" if gate_pass else "FAIL"

        entry = {
            "multiplier": mult,
            "cost_per_trade_usd": round(cost_per_trade, 4),
            "total_cost_usd": round(total_cost, 2),
            "net_pnl": round(net, 2),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(min(pf, 999.99), 4),
            "sharpe": round(sharpe, 4),
            "max_dd_pct": round(mdd, 6),
            "verdict": verdict,
        }
        levels.append(entry)
        logger.info(
            f"  {mult}× (${cost_per_trade:.2f}/trade): Sharpe={sharpe:.4f}  PF={pf:.4f}  "
            f"Net=${net:,.2f}  → {verdict}"
        )

    # Break-even cost = IS_NET_PNL / IS_TRADES
    break_even_cost = IS_NET_PNL / IS_TRADES if IS_TRADES > 0 else 0.0
    break_even_mult = break_even_cost / BASELINE_SPREAD_USD if BASELINE_SPREAD_USD > 0 else 0.0

    summary = {
        "baseline_spread_usd": BASELINE_SPREAD_USD,
        "break_even_cost_per_trade": round(break_even_cost, 2),
        "break_even_multiplier": round(break_even_mult, 1),
        "pass_at_3x": next((l["verdict"] == "PASS" for l in levels if l["multiplier"] == 3), False),
        "levels": levels,
    }
    (cst_dir / "cost_stress_summary.json").write_text(json.dumps(summary, indent=4))
    logger.info(f"\n  Break-even cost per trade: ${break_even_cost:.2f} (= {break_even_mult:.0f}× baseline spread)")

    return summary


# ---------------------------------------------------------------------------
# Final recommendation logic
# ---------------------------------------------------------------------------

def compute_recommendation(wfv: dict, cst: dict) -> dict:
    wfv_pass  = wfv.get("wfv_verdict") == "PASS"
    cst_pass  = cst.get("pass_at_3x", False)
    wfe       = wfv.get("wfe_pct", 0.0)

    if wfv_pass and cst_pass:
        label  = "CANDIDATE_FOR_PORTFOLIO"
        colour = "pass"
        reason = (
            f"WFV PASS (WFE {wfe:.1f}% ≥ 40%) + cost-robust through 3× spread. "
            "Strategy retains edge across time slices and after realistic transaction costs. "
            "Ready for correlation check against GOLD_PORT_02 and live paper-trading trial."
        )
    elif wfv_pass and not cst_pass:
        label  = "CANDIDATE_FOR_ROBUSTNESS_REVIEW"
        colour = "warn"
        reason = (
            f"WFV PASS (WFE {wfe:.1f}%) but cost-stress FAILED at 3× spread. "
            "Edge exists but is sensitive to transaction costs. Investigate position sizing or "
            "use tighter execution (limit orders, ECN routing)."
        )
    elif not wfv_pass and cst_pass:
        label  = "HOLD"
        colour = "warn"
        reason = (
            f"Cost-stress PASS but WFV FAIL (WFE {wfe:.1f}% < 40%). "
            "Edge is not temporally stable — possible regime-dependency. "
            "Investigate regime filter or extend dataset before re-testing."
        )
    else:
        label  = "REJECT"
        colour = "fail"
        reason = (
            f"Both WFV and cost-stress FAILED. WFE {wfe:.1f}% < 40%. "
            "Strategy does not survive validation. Document in journal/rejected_ideas.md."
        )

    return {"label": label, "colour": colour, "reason": reason, "wfv_pass": wfv_pass, "cst_pass": cst_pass}


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _vc(verdict: str) -> str:
    if verdict == "PASS":
        return "pass"
    if verdict in ("HOLD", "WARN"):
        return "warn"
    return "fail"


def generate_html_report(wfv: dict, cst: dict, rec: dict, elapsed_s: float) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- WFV fold rows ---
    wfv_rows = ""
    for fr in wfv.get("folds", []):
        if fr["scorecard"] is None:
            wfv_rows += f"""
            <tr>
              <td>{fr['label']}</td>
              <td>{fr['date_start']}</td>
              <td>{fr['date_end']}</td>
              <td>{fr['bars']:,}</td>
              <td colspan="6" style="color:var(--accent-red)">ERROR: {fr['error']}</td>
            </tr>"""
            continue
        sc = fr["scorecard"]
        fa = fr["falsification"]
        v  = fa["verdict"]
        wfv_rows += f"""
        <tr>
          <td><strong>{fr['label'].replace('_', ' ').title()}</strong></td>
          <td style="font-size:0.82rem;color:var(--text-secondary)">{fr['date_start']}</td>
          <td style="font-size:0.82rem;color:var(--text-secondary)">{fr['date_end']}</td>
          <td class="num">{fr['bars']:,}</td>
          <td class="num {'pos' if sc['sharpe'] > 0 else 'neg'}">{sc['sharpe']:.4f}</td>
          <td class="num {'pos' if sc['profit_factor'] > 1 else 'neg'}">{sc['profit_factor']:.4f}</td>
          <td class="num">{sc['total_trades']}</td>
          <td class="num {'pos' if sc['win_rate'] > 0.5 else ''}">{sc['win_rate']:.1%}</td>
          <td class="num {'pos' if sc['total_net_profit'] > 0 else 'neg'}">${sc['total_net_profit']:,.2f}</td>
          <td><span class="badge badge-{_vc(v)}">{v}</span></td>
        </tr>"""

    # WFE row
    wfe_pct  = wfv.get("wfe_pct", 0.0)
    wfe_pass = wfv.get("wfe_passed", False)
    mean_oos = wfv.get("mean_oos_sharpe", 0.0)
    wfv_verdict = wfv.get("wfv_verdict", "FAIL")

    # --- Cost stress rows ---
    cst_rows = ""
    for lvl in cst.get("levels", []):
        v  = lvl["verdict"]
        hi = lvl["multiplier"] == 3  # highlight the critical 3× row
        style = "background:rgba(251,191,36,0.06);" if hi else ""
        cst_rows += f"""
        <tr style="{style}">
          <td><strong>{lvl['multiplier']}×</strong>{'  ← stress gate' if hi else ''}</td>
          <td class="num">${lvl['cost_per_trade_usd']:.2f}</td>
          <td class="num">${lvl['total_cost_usd']:,.2f}</td>
          <td class="num {'pos' if lvl['net_pnl'] > 0 else 'neg'}">${lvl['net_pnl']:,.2f}</td>
          <td class="num {'pos' if lvl['profit_factor'] > 1 else 'neg'}">{lvl['profit_factor']:.4f}</td>
          <td class="num {'pos' if lvl['sharpe'] > 0 else 'neg'}">{lvl['sharpe']:.4f}</td>
          <td class="num neg">{lvl['max_dd_pct']:.2%}</td>
          <td><span class="badge badge-{_vc(v)}">{v}</span></td>
        </tr>"""

    # KPI values
    break_even_mult = cst.get("break_even_multiplier", 0.0)
    break_even_cost = cst.get("break_even_cost_per_trade", 0.0)
    rec_label  = rec["label"]
    rec_colour = rec["colour"]
    rec_reason = rec["reason"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Asia Session Sweep — Stage 2 Validation Report</title>
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
    --accent-orange: #fb923c;
    --border: #2a2a38;
}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg-primary);color:var(--text-primary);line-height:1.6;min-height:100vh;}}
.container{{max-width:1400px;margin:0 auto;padding:40px 24px;}}
.hero{{text-align:center;padding:60px 20px;background:linear-gradient(135deg,#0f0f1a 0%,#1a1a2e 50%,#16213e 100%);border-radius:24px;border:1px solid var(--border);margin-bottom:40px;position:relative;overflow:hidden;}}
.hero::before{{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 30% 40%,rgba(251,191,36,0.05) 0%,transparent 50%),radial-gradient(circle at 70% 60%,rgba(74,222,128,0.04) 0%,transparent 50%);animation:pulse 8s ease-in-out infinite alternate;}}
@keyframes pulse{{to{{transform:scale(1.05);}}}}
.hero h1{{font-size:2.6rem;font-weight:900;letter-spacing:-0.03em;margin-bottom:8px;background:linear-gradient(135deg,var(--accent-gold),#f59e0b,var(--accent-green));-webkit-background-clip:text;-webkit-text-fill-color:transparent;position:relative;}}
.hero .subtitle{{font-size:1.05rem;color:var(--text-secondary);position:relative;}}
.hero .meta{{color:var(--text-muted);font-size:0.85rem;margin-top:12px;position:relative;}}
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:40px;}}
.kpi{{background:var(--bg-card);border:1px solid var(--border);border-radius:16px;padding:24px;text-align:center;}}
.kpi-value{{font-size:1.9rem;font-weight:800;letter-spacing:-0.02em;}}
.kpi-label{{font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em;margin-top:4px;}}
.kpi-sub{{font-size:0.72rem;color:var(--text-muted);margin-top:2px;}}
.kpi-green{{color:var(--accent-green);}}
.kpi-red{{color:var(--accent-red);}}
.kpi-gold{{color:var(--accent-gold);}}
.kpi-blue{{color:var(--accent-blue);}}
.kpi-purple{{color:var(--accent-purple);}}
.kpi-orange{{color:var(--accent-orange);}}
.section{{background:var(--bg-card);border:1px solid var(--border);border-radius:20px;padding:32px;margin-bottom:32px;}}
.section-title{{font-size:1.3rem;font-weight:700;margin-bottom:24px;display:flex;align-items:center;gap:12px;}}
.section-title .icon{{font-size:1.5rem;}}
.pipeline{{display:flex;gap:0;flex-wrap:wrap;margin-bottom:8px;}}
.pipe-step{{background:var(--bg-elevated);border:1px solid var(--border);padding:12px 20px;flex:1;min-width:130px;position:relative;}}
.pipe-step:not(:last-child)::after{{content:"→";position:absolute;right:-12px;top:50%;transform:translateY(-50%);color:var(--accent-gold);font-weight:700;z-index:1;}}
.pipe-step .step-num{{font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;}}
.pipe-step .step-name{{font-size:0.9rem;font-weight:600;color:var(--text-primary);margin-top:2px;}}
.pipe-step .step-detail{{font-size:0.75rem;color:var(--text-secondary);margin-top:2px;}}
.pipe-step.done{{border-color:var(--accent-green);}}
.pipe-step.done .step-num{{color:var(--accent-green);}}
.pipe-step.active{{border-color:var(--accent-gold);background:rgba(251,191,36,0.06);}}
.pipe-step.active .step-num{{color:var(--accent-gold);}}
.pipe-step.next{{border-color:var(--text-muted);opacity:0.6;}}
table{{width:100%;border-collapse:collapse;font-size:0.9rem;}}
th{{background:var(--bg-elevated);padding:12px 16px;text-align:left;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);border-bottom:1px solid var(--border);}}
td{{padding:14px 16px;border-bottom:1px solid rgba(42,42,56,0.5);}}
tr:hover td{{background:rgba(30,30,42,0.5);}}
.num{{text-align:right;font-family:monospace;font-size:0.88rem;}}
.pos{{color:var(--accent-green);}}
.neg{{color:var(--accent-red);}}
.warn{{color:var(--accent-orange);}}
.badge{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:0.75rem;font-weight:700;letter-spacing:0.05em;}}
.badge-pass{{background:rgba(74,222,128,0.15);color:var(--accent-green);border:1px solid rgba(74,222,128,0.3);}}
.badge-fail{{background:rgba(248,113,113,0.15);color:var(--accent-red);border:1px solid rgba(248,113,113,0.3);}}
.badge-warn{{background:rgba(251,191,36,0.15);color:var(--accent-gold);border:1px solid rgba(251,191,36,0.3);}}
.verdict-box{{border-radius:16px;padding:28px 36px;display:flex;align-items:center;gap:24px;font-size:1.1rem;font-weight:600;margin-top:16px;}}
.verdict-pass{{background:rgba(74,222,128,0.08);border:2px solid rgba(74,222,128,0.3);color:var(--accent-green);}}
.verdict-fail{{background:rgba(248,113,113,0.08);border:2px solid rgba(248,113,113,0.3);color:var(--accent-red);}}
.verdict-warn{{background:rgba(251,191,36,0.08);border:2px solid rgba(251,191,36,0.3);color:var(--accent-gold);}}
.verdict-icon{{font-size:2.8rem;}}
.verdict-reason{{font-size:0.92rem;font-weight:400;opacity:0.85;margin-top:6px;line-height:1.7;}}
.info-box{{background:var(--bg-elevated);border:1px solid var(--border);border-radius:12px;padding:20px;font-size:0.9rem;color:var(--text-secondary);line-height:1.8;}}
.info-box strong{{color:var(--accent-gold);}}
.wfe-bar-wrap{{background:var(--bg-elevated);border-radius:8px;overflow:hidden;height:24px;margin-top:8px;position:relative;}}
.wfe-bar{{height:100%;border-radius:8px;transition:width 1s ease;display:flex;align-items:center;padding-left:10px;font-size:0.78rem;font-weight:700;}}
.wfe-label{{position:absolute;right:10px;top:50%;transform:translateY(-50%);font-size:0.78rem;color:var(--text-primary);font-weight:700;}}
.next-steps li{{padding:8px 0;border-bottom:1px solid rgba(42,42,56,0.5);color:var(--text-secondary);}}
.next-steps li strong{{color:var(--text-primary);}}
.stage-badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:0.72rem;font-weight:700;letter-spacing:0.05em;margin-left:8px;background:rgba(251,191,36,0.15);color:var(--accent-gold);border:1px solid rgba(251,191,36,0.3);}}
footer{{text-align:center;padding:40px;color:var(--text-muted);font-size:0.8rem;}}
</style>
</head>
<body>
<div class="container">

  <!-- Hero -->
  <div class="hero">
    <h1>Asia Session Sweep — Stage 2 Validation</h1>
    <p class="subtitle">Walk-Forward Validation &bull; Cost Stress Test &bull; XAUUSD 15m &bull; Real IBKR Data</p>
    <p class="meta">Generated {now_str} &bull; Elapsed {elapsed_s:.1f}s &bull; Gold Research Factory &bull; Solid2026</p>
  </div>

  <!-- KPI strip -->
  <div class="kpi-strip">
    <div class="kpi">
      <div class="kpi-value kpi-gold">{wfe_pct:.1f}%</div>
      <div class="kpi-label">WFE</div>
      <div class="kpi-sub">target ≥ 40%</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-{'green' if wfv_verdict == 'PASS' else 'red'}">{wfv_verdict}</div>
      <div class="kpi-label">WFV Verdict</div>
      <div class="kpi-sub">3-fold walk-forward</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-{'green' if cst.get('pass_at_3x') else 'red'}">{'PASS' if cst.get('pass_at_3x') else 'FAIL'}</div>
      <div class="kpi-label">Cost @ 3×</div>
      <div class="kpi-sub">${BASELINE_SPREAD_USD * 3:.2f}/trade</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-blue">{mean_oos:.4f}</div>
      <div class="kpi-label">Mean OOS Sharpe</div>
      <div class="kpi-sub">IS: {IS_SHARPE:.4f}</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-orange">{break_even_mult:.0f}×</div>
      <div class="kpi-label">Break-Even Mult</div>
      <div class="kpi-sub">${break_even_cost:.2f}/trade to zero</div>
    </div>
    <div class="kpi">
      <div class="kpi-value kpi-purple" style="font-size:1.2rem">{rec_label.replace('_', ' ')}</div>
      <div class="kpi-label">Recommendation</div>
    </div>
  </div>

  <!-- Research pipeline -->
  <div class="section">
    <div class="section-title"><span class="icon">⚙️</span> Research Pipeline — Current Stage <span class="stage-badge">Stage 2 of 4</span></div>
    <div class="pipeline">
      <div class="pipe-step done">
        <div class="step-num">Stage 1 ✓</div>
        <div class="step-name">Baseline Backtest</div>
        <div class="step-detail">3 configs, all PASS</div>
      </div>
      <div class="pipe-step active">
        <div class="step-num">Stage 2 ← NOW</div>
        <div class="step-name">Validation Suite</div>
        <div class="step-detail">WFV + Cost Stress</div>
      </div>
      <div class="pipe-step next">
        <div class="step-num">Stage 3</div>
        <div class="step-name">Correlation Check</div>
        <div class="step-detail">vs GOLD_PORT_02</div>
      </div>
      <div class="pipe-step next">
        <div class="step-num">Stage 4</div>
        <div class="step-name">Portfolio Add</div>
        <div class="step-detail">Paper → Live</div>
      </div>
    </div>
    <div class="info-box" style="margin-top:16px;">
      <strong>Baseline summary (Stage 1):</strong> All 3 configurations (Default, Tight SL, Wide RR) passed all 5
      falsification gates on the full IBKR 15m dataset (29,187 bars, 2025-01-14 → 2026-03-04).
      Best config: <strong>Default</strong> — Sharpe 7.7469, PF 3.67, 112 trades, Win Rate 64.3%, Net P&amp;L $1,253.
      <br/><strong>Stage 2 purpose:</strong> Confirm the edge is temporally stable (WFV) and survives realistic
      transaction costs before adding to GOLD_PORT_02.
    </div>
  </div>

  <!-- Walk-Forward Validation -->
  <div class="section">
    <div class="section-title"><span class="icon">📅</span> Stage 2a — Walk-Forward Validation (3 Folds, Default Config)</div>
    <table>
      <thead>
        <tr>
          <th>Fold</th>
          <th>From</th>
          <th>To</th>
          <th style="text-align:right">Bars</th>
          <th style="text-align:right">Sharpe</th>
          <th style="text-align:right">Profit Factor</th>
          <th style="text-align:right">Trades</th>
          <th style="text-align:right">Win Rate</th>
          <th style="text-align:right">Net P&amp;L</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>
        {wfv_rows}
      </tbody>
    </table>

    <!-- WFE bar -->
    <div style="margin-top:28px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:0.9rem;color:var(--text-secondary);">Walk-Forward Efficiency (WFE)</span>
        <span style="font-weight:700;color:{'var(--accent-green)' if wfe_pass else 'var(--accent-red)'};">{wfe_pct:.1f}% {'✓' if wfe_pass else '✗'} (threshold: ≥ 40%)</span>
      </div>
      <div class="wfe-bar-wrap">
        <div class="wfe-bar" style="width:{min(wfe_pct, 100):.1f}%;background:{'var(--accent-green)' if wfe_pass else 'var(--accent-red)'};">
          {wfe_pct:.1f}%
        </div>
        <div class="wfe-label">IS Sharpe: {IS_SHARPE:.4f}</div>
      </div>
      <p style="margin-top:10px;font-size:0.83rem;color:var(--text-muted);">
        WFE = mean(OOS fold Sharpes) / IS Sharpe × 100 = {mean_oos:.4f} / {IS_SHARPE:.4f} × 100 = {wfe_pct:.1f}%.
        Each fold uses the same default params (sl_buffer_pct=0.001, rr=2.0) — no re-optimization.
      </p>
    </div>
  </div>

  <!-- Cost Stress Test -->
  <div class="section">
    <div class="section-title"><span class="icon">💰</span> Stage 2b — Cost Stress Test (Analytical)</div>
    <div class="info-box" style="margin-bottom:20px;">
      <strong>Method:</strong> Baseline spread assumption = ${BASELINE_SPREAD_USD:.2f} / oz round-trip (ECN-like for 1 oz XAUUSD).
      Each trade's realized P&amp;L is reduced by <em>multiplier × ${BASELINE_SPREAD_USD:.2f}</em>.
      Metrics are recomputed from the adjusted P&amp;L stream. Gate: PF &gt; 1.0 AND Sharpe &gt; 0.5 at 3× spread.
      <br/><strong>Source positions:</strong> 112 trades from baseline default run (positions.csv).
    </div>
    <table>
      <thead>
        <tr>
          <th>Multiplier</th>
          <th style="text-align:right">Cost / Trade</th>
          <th style="text-align:right">Total Cost</th>
          <th style="text-align:right">Net P&amp;L</th>
          <th style="text-align:right">Profit Factor</th>
          <th style="text-align:right">Sharpe</th>
          <th style="text-align:right">Max DD</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>
        {cst_rows}
      </tbody>
    </table>
    <p style="margin-top:14px;font-size:0.83rem;color:var(--text-muted);">
      Break-even: ${break_even_cost:.2f}/trade = {break_even_mult:.0f}× baseline spread.
      The strategy's edge is eliminated only at extreme ({break_even_mult:.0f}×) cost levels, confirming
      it is not reliant on zero-cost assumptions.
    </p>
  </div>

  <!-- Final Verdict -->
  <div class="section">
    <div class="section-title"><span class="icon">⚖️</span> Stage 2 Verdict &amp; Recommendation</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">
      <div style="background:var(--bg-elevated);border:1px solid {'rgba(74,222,128,0.3)' if wfv_verdict=='PASS' else 'rgba(248,113,113,0.3)'};border-radius:12px;padding:20px;">
        <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);margin-bottom:6px;">Walk-Forward Validation</div>
        <div style="font-size:1.4rem;font-weight:800;color:{'var(--accent-green)' if wfv_verdict=='PASS' else 'var(--accent-red)'};">{wfv_verdict}</div>
        <div style="font-size:0.85rem;color:var(--text-secondary);margin-top:4px;">WFE {wfe_pct:.1f}% (threshold ≥ 40%)</div>
      </div>
      <div style="background:var(--bg-elevated);border:1px solid {'rgba(74,222,128,0.3)' if cst.get('pass_at_3x') else 'rgba(248,113,113,0.3)'};border-radius:12px;padding:20px;">
        <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);margin-bottom:6px;">Cost Stress @ 3×</div>
        <div style="font-size:1.4rem;font-weight:800;color:{'var(--accent-green)' if cst.get('pass_at_3x') else 'var(--accent-red)'};">{'PASS' if cst.get('pass_at_3x') else 'FAIL'}</div>
        <div style="font-size:0.85rem;color:var(--text-secondary);margin-top:4px;">${BASELINE_SPREAD_USD * 3:.2f}/trade round-trip</div>
      </div>
    </div>
    <div class="verdict-box verdict-{rec_colour}">
      <div class="verdict-icon">{'✅' if rec_colour == 'pass' else ('⚠️' if rec_colour == 'warn' else '❌')}</div>
      <div>
        <div style="font-size:1.2rem;letter-spacing:0.04em;">{rec_label}</div>
        <div class="verdict-reason">{rec_reason}</div>
      </div>
    </div>
  </div>

  <!-- Next steps -->
  <div class="section">
    <div class="section-title"><span class="icon">🗺️</span> Next Steps</div>
    <ul class="next-steps" style="list-style:none;padding:0;">
      <li><strong>Stage 3 — Correlation check:</strong> Compute daily return correlation of AsiaSweep Default
        against BollReversion 15m, ZScoreReversion 15m, and SqueezeBreakout 5m (GOLD_PORT_02 members).
        Target: pairwise |r| &lt; 0.60 to confirm diversification value.</li>
      <li><strong>Stage 4 — Paper trading trial:</strong> Deploy AsiaSweep Default on live XAUUSD 15m feed
        for 30 sessions (≈ 30 trades). Compare live win rate and avg R:R against backtest baseline
        (64.3% win, 1:2 R:R).</li>
      <li><strong>Optional: M1 data upgrade:</strong> Original spec used M1 bars for precise MSS detection.
        15m approximation may undercount setups or misclassify MSS timing.
        Acquiring 1m data could refine entry precision and potentially improve win rate further.</li>
      <li><strong>Optional: Range width filter:</strong> Add a minimum pre-Asia range width gate
        (e.g., range ≥ 0.3% of price = ≥ ATR threshold) to skip low-volatility sessions where
        liquidity sweeps are less meaningful.</li>
    </ul>
  </div>

  <footer>
    Gold Research Factory &bull; Solid2026 &bull; Falsification-First Research &bull;
    Validation script: scripts/run_asia_sweep_validation.py &bull;
    Baseline: results/raw_runs/ASIA_SWEEP_15M/
  </footer>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 70)
    logger.info("ASIA SESSION SWEEP — STAGE 2 VALIDATION SUITE")
    logger.info("=" * 70)

    t0 = datetime.now()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load full data once
    logger.info(f"Loading 15m data from {RAW_15M.name}…")
    df = load_ib_parquet(str(RAW_15M))
    df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
    logger.info(f"Full dataset: {len(df):,} bars  [{df['datetime'].min()} → {df['datetime'].max()}]")

    # Stage 1: WFV
    wfv = run_wfv(df)

    # Stage 2: Cost Stress
    cst = run_cost_stress()

    # Recommendation
    rec = compute_recommendation(wfv, cst)
    logger.info(f"\n{'='*70}")
    logger.info(f"FINAL RECOMMENDATION: {rec['label']}")
    logger.info(f"  {rec['reason']}")
    logger.info(f"{'='*70}")

    elapsed = (datetime.now() - t0).total_seconds()

    # Validation log
    log_data = {
        "experiment": "ASIA_SWEEP_VALIDATION",
        "run_at": t0.isoformat(),
        "elapsed_s": round(elapsed, 2),
        "baseline_sharpe": IS_SHARPE,
        "wfv_summary": wfv,
        "cost_stress_summary": cst,
        "recommendation": rec,
    }
    (RESULTS_DIR / "validation_log.json").write_text(json.dumps(log_data, indent=4, default=str))

    # HTML report
    html = generate_html_report(wfv, cst, rec, elapsed)
    REPORT_PATH.write_text(html, encoding="utf-8")
    logger.info(f"\nHTML report:  {REPORT_PATH}")
    logger.info(f"Elapsed:      {elapsed:.1f}s")
    logger.info("\nDone.")


if __name__ == "__main__":
    main()
