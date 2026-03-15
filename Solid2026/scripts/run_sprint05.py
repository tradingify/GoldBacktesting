"""
Sprint 05: Real Data Portfolio Assembly
=======================================
Builds GOLD_PORT_02 from the 3 strategies that passed Sprint 04 real-data validation:
  1. BollReversion 15m
  2. ZScoreReversion 15m
  3. SqueezeBreakout 5m

Steps:
  1. Extract daily PnL series from each strategy's positions.csv
  2. Compute pairwise correlations
  3. Inverse-volatility weighting
  4. Simulate blended portfolio equity curve
  5. Compute portfolio-level metrics
  6. Save portfolio card + tracker JSON
"""
import sys, json, os, logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s | sprint_05 | %(levelname)s | %(message)s")
log = logging.getLogger("sprint_05")

# ─── Config ───
BASE = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs\SPRINT_04_REAL")
OUT_DIR = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs\SPRINT_05_PORTFOLIO")
OUT_DIR.mkdir(parents=True, exist_ok=True)

INITIAL_CAPITAL = 100_000.0

STRATEGIES = [
    {"name": "BollReversion",    "tf": "15m", "run_id": "run_BollReversion_15m_2493_real"},
    {"name": "ZScoreReversion",  "tf": "15m", "run_id": "run_ZScoreReversion_15m_8360_real"},
    {"name": "SqueezeBreakout",  "tf": "5m",  "run_id": "run_SqueezeBreakout_5m_5587_real"},
]


def parse_pnl(val):
    """Parse PnL from Nautilus format '1.23 USD' or float."""
    s = str(val).replace(" USD", "").replace(",", "")
    try:
        return float(s)
    except:
        return 0.0


def load_daily_pnl(run_id: str) -> pd.Series:
    """Load positions.csv and aggregate to daily PnL series."""
    pos_path = BASE / run_id / "positions.csv"
    df = pd.read_csv(pos_path)
    
    # Parse close timestamps and PnL
    df["close_dt"] = pd.to_datetime(df["ts_closed"], utc=True)
    df["pnl"] = df["realized_pnl"].apply(parse_pnl)
    
    # Aggregate to daily
    df["date"] = df["close_dt"].dt.date
    daily = df.groupby("date")["pnl"].sum()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()
    
    return daily


def compute_metrics(equity_curve: pd.Series, daily_returns: pd.Series) -> dict:
    """Compute portfolio-level performance metrics."""
    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
    net_pnl = equity_curve.iloc[-1] - equity_curve.iloc[0]
    
    # Sharpe (annualized)
    if daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0
    
    # Sortino
    downside = daily_returns[daily_returns < 0]
    if len(downside) > 0 and downside.std() > 0:
        sortino = (daily_returns.mean() / downside.std()) * np.sqrt(252)
    else:
        sortino = 0.0
    
    # Max Drawdown
    cummax = equity_curve.cummax()
    drawdown = (equity_curve - cummax) / cummax
    max_dd = drawdown.min()
    
    # Calmar
    calmar = (total_return * 252 / len(daily_returns)) / abs(max_dd) if max_dd != 0 else 0.0
    
    # Profit Factor
    gross_profit = daily_returns[daily_returns > 0].sum()
    gross_loss = abs(daily_returns[daily_returns < 0].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else 0.0
    
    # Win rate (daily)
    win_days = (daily_returns > 0).sum()
    total_days = len(daily_returns)
    win_rate = win_days / total_days if total_days > 0 else 0.0
    
    return {
        "total_return_pct": round(total_return * 100, 2),
        "net_pnl": round(net_pnl, 2),
        "final_equity": round(equity_curve.iloc[-1], 2),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4),
        "profit_factor": round(pf, 4),
        "max_drawdown_pct": round(max_dd * 100, 4),
        "win_rate_daily": round(win_rate * 100, 2),
        "total_trading_days": total_days,
    }


# ═══════════════════════════════════════════════════
#  STEP 1: Extract daily PnL for each strategy
# ═══════════════════════════════════════════════════
log.info("=" * 60)
log.info("SPRINT 05: REAL DATA PORTFOLIO ASSEMBLY")
log.info("=" * 60)

daily_pnls = {}
strategy_metrics = {}

for s in STRATEGIES:
    label = f"{s['name']}/{s['tf']}"
    log.info(f"Loading {label}...")
    pnl = load_daily_pnl(s["run_id"])
    daily_pnls[label] = pnl
    
    # Build equity curve for individual strategy
    equity = INITIAL_CAPITAL + pnl.cumsum()
    returns = pnl / INITIAL_CAPITAL  # Simple returns on initial capital
    metrics = compute_metrics(equity, returns)
    strategy_metrics[label] = metrics
    
    log.info(f"  {label}: {len(pnl)} trading days, Net=${metrics['net_pnl']:,.2f}, Sharpe={metrics['sharpe']:.2f}")

# ═══════════════════════════════════════════════════
#  STEP 2: Correlation Analysis
# ═══════════════════════════════════════════════════
log.info("")
log.info("CORRELATION ANALYSIS")
log.info("-" * 40)

# Align all series to the same date index
all_dates = sorted(set().union(*(pnl.index for pnl in daily_pnls.values())))
aligned = pd.DataFrame(index=all_dates)
for label, pnl in daily_pnls.items():
    aligned[label] = pnl
aligned = aligned.fillna(0)

corr_matrix = aligned.corr()
log.info("Pairwise Correlations:")
labels = list(daily_pnls.keys())
correlations = {}
for i in range(len(labels)):
    for j in range(i + 1, len(labels)):
        rho = corr_matrix.loc[labels[i], labels[j]]
        pair = f"{labels[i]} vs {labels[j]}"
        correlations[pair] = round(rho, 4)
        log.info(f"  {pair}: ρ = {rho:.4f}")

# ═══════════════════════════════════════════════════
#  STEP 3: Inverse-Volatility Weighting
# ═══════════════════════════════════════════════════
log.info("")
log.info("INVERSE-VOLATILITY WEIGHTING")
log.info("-" * 40)

vols = {}
for label in labels:
    vol = aligned[label].std()
    vols[label] = vol
    log.info(f"  {label}: daily vol = ${vol:.2f}")

inv_vols = {k: 1.0 / v if v > 0 else 0.0 for k, v in vols.items()}
total_inv = sum(inv_vols.values())
weights = {k: round(v / total_inv, 4) for k, v in inv_vols.items()}

for label, w in weights.items():
    log.info(f"  {label}: weight = {w:.1%}")

# ═══════════════════════════════════════════════════
#  STEP 4: Simulate Blended Portfolio
# ═══════════════════════════════════════════════════
log.info("")
log.info("PORTFOLIO SIMULATION")
log.info("-" * 40)

# Weighted daily PnL
portfolio_daily_pnl = pd.Series(0.0, index=aligned.index)
for label in labels:
    portfolio_daily_pnl += aligned[label] * weights[label]

# Portfolio equity curve
portfolio_equity = INITIAL_CAPITAL + portfolio_daily_pnl.cumsum()
portfolio_returns = portfolio_daily_pnl / INITIAL_CAPITAL

portfolio_metrics = compute_metrics(portfolio_equity, portfolio_returns)

log.info(f"  Final Equity:   ${portfolio_metrics['final_equity']:,.2f}")
log.info(f"  Net PnL:        ${portfolio_metrics['net_pnl']:,.2f}")
log.info(f"  Total Return:   {portfolio_metrics['total_return_pct']:.2f}%")
log.info(f"  Sharpe Ratio:   {portfolio_metrics['sharpe']:.4f}")
log.info(f"  Sortino Ratio:  {portfolio_metrics['sortino']:.4f}")
log.info(f"  Profit Factor:  {portfolio_metrics['profit_factor']:.4f}")
log.info(f"  Max Drawdown:   {portfolio_metrics['max_drawdown_pct']:.4f}%")
log.info(f"  Calmar Ratio:   {portfolio_metrics['calmar']:.4f}")
log.info(f"  Win Rate:       {portfolio_metrics['win_rate_daily']:.1f}% of days")
log.info(f"  Trading Days:   {portfolio_metrics['total_trading_days']}")

# ═══════════════════════════════════════════════════
#  STEP 5: Save Results
# ═══════════════════════════════════════════════════
portfolio_card = {
    "portfolio_id": "GOLD_PORT_02",
    "created_at": datetime.now().isoformat(),
    "data_source": "real_ibkr",
    "initial_capital": INITIAL_CAPITAL,
    "strategies": [
        {
            "name": s["name"],
            "timeframe": s["tf"],
            "run_id": s["run_id"],
            "weight": weights[f"{s['name']}/{s['tf']}"],
            "individual_metrics": strategy_metrics[f"{s['name']}/{s['tf']}"],
        }
        for s in STRATEGIES
    ],
    "correlations": correlations,
    "weights_method": "inverse_volatility",
    "portfolio_metrics": portfolio_metrics,
}

# Save portfolio card
card_path = OUT_DIR / "GOLD_PORT_02_card.json"
with open(card_path, "w") as f:
    json.dump(portfolio_card, f, indent=4, default=str)
log.info(f"\nPortfolio card saved: {card_path}")

# Save equity curves as CSV
equity_df = pd.DataFrame({
    "date": aligned.index,
    "BollReversion_15m_pnl": aligned[labels[0]].values,
    "ZScoreReversion_15m_pnl": aligned[labels[1]].values,
    "SqueezeBreakout_5m_pnl": aligned[labels[2]].values,
    "portfolio_pnl": portfolio_daily_pnl.values,
    "portfolio_equity": portfolio_equity.values,
})
equity_path = OUT_DIR / "equity_curves.csv"
equity_df.to_csv(equity_path, index=False)
log.info(f"Equity curves saved: {equity_path}")

# Save correlation matrix
corr_path = OUT_DIR / "correlation_matrix.csv"
corr_matrix.to_csv(corr_path)
log.info(f"Correlation matrix saved: {corr_path}")

log.info("")
log.info("=" * 60)
log.info("SPRINT 05 COMPLETE — GOLD_PORT_02 ASSEMBLED")
log.info("=" * 60)
