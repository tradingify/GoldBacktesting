"""
Sprint 04: Real Data Validation Runner
=======================================
Runs all 10 GOLD_PORT_01 strategies against real IBKR bar data.

For each strategy:
  1. Loads real parquet via ib_loader
  2. Converts to Nautilus Bar objects via bar_builder 
  3. Configures BacktestEngine with proper instrument + venue
  4. Instantiates strategy with frozen Sprint 02 params
  5. Runs engine
  6. Extracts equity curve + trade log from engine
  7. Generates real scorecard via generate_scorecard()
  8. Updates sprint_04_tracker.json
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Ensure project is on path
sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")

import pandas as pd
import numpy as np

from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.data.ingest.bar_builder import df_to_nautilus_bars
from src.gold_research.analytics.scorecards import StrategyScorecard, generate_scorecard
from src.gold_research.analytics.metrics import sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio
from src.gold_research.core.paths import ProjectPaths

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.objects import Price, Quantity, Money, Currency
from nautilus_trader.config import LoggingConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("sprint_04")

# ===========================================================================
# CONFIGURATION: The 10 strategies to test
# ===========================================================================
REAL_DATA_DIR = Path(r"D:\.openclaw\GoldBacktesting\bars")

# Map timeframe to parquet file name
TF_TO_FILE = {
    "5m":  REAL_DATA_DIR / "xauusd_5_mins.parquet",
    "15m": REAL_DATA_DIR / "xauusd_15_mins.parquet",
    "1h":  REAL_DATA_DIR / "xauusd_1_hour.parquet",
    "4h":  REAL_DATA_DIR / "xauusd_4_hours.parquet",
}

# Strategy definitions — frozen from Sprint 02 outcomes
STRATEGIES = [
    {
        "run_id": "run_Donchian_5m_4244_real",
        "original_run_id": "run_Donchian_5m_4244",
        "name": "Donchian",
        "tf": "5m",
        "class_path": "src.gold_research.strategies.trend.donchian_breakout.DonchianBreakout",
        "config_class_path": "src.gold_research.strategies.trend.donchian_breakout.DonchianBreakoutConfig",
        "params": {"channel_lookback": 20, "trail_atr_multiplier": 2.0},
        "synthetic_sharpe": 2.13,
        "synthetic_pf": 2.16,
    },
    {
        "run_id": "run_SqueezeBreakout_5m_5587_real",
        "original_run_id": "run_SqueezeBreakout_5m_5587",
        "name": "SqueezeBreakout",
        "tf": "5m",
        "class_path": "src.gold_research.strategies.breakout.squeeze_breakout.SqueezeBreakout",
        "config_class_path": "src.gold_research.strategies.breakout.squeeze_breakout.SqueezeBreakoutConfig",
        "params": {"bb_period": 20, "kc_period": 20, "trail_atr_multiplier": 2.0},
        "synthetic_sharpe": 0.67,
        "synthetic_pf": 1.05,
    },
    {
        "run_id": "run_Donchian_1h_8942_real",
        "original_run_id": "run_Donchian_1h_8942",
        "name": "Donchian",
        "tf": "1h",
        "class_path": "src.gold_research.strategies.trend.donchian_breakout.DonchianBreakout",
        "config_class_path": "src.gold_research.strategies.trend.donchian_breakout.DonchianBreakoutConfig",
        "params": {"channel_lookback": 20, "trail_atr_multiplier": 2.0},
        "synthetic_sharpe": 1.84,
        "synthetic_pf": 1.65,
    },
    {
        "run_id": "run_BollReversion_15m_2493_real",
        "original_run_id": "run_BollReversion_15m_2493",
        "name": "BollReversion",
        "tf": "15m",
        "class_path": "src.gold_research.strategies.mean_reversion.bollinger_reversion.BollingerReversion",
        "config_class_path": "src.gold_research.strategies.mean_reversion.bollinger_reversion.BollingerReversionConfig",
        "params": {"period": 20, "std_devs": 2.0, "hold_bars": 5},
        "synthetic_sharpe": 2.15,
        "synthetic_pf": 2.25,
    },
    {
        "run_id": "run_SqueezeBreakout_15m_2908_real",
        "original_run_id": "run_SqueezeBreakout_15m_2908",
        "name": "SqueezeBreakout",
        "tf": "15m",
        "class_path": "src.gold_research.strategies.breakout.squeeze_breakout.SqueezeBreakout",
        "config_class_path": "src.gold_research.strategies.breakout.squeeze_breakout.SqueezeBreakoutConfig",
        "params": {"bb_period": 20, "kc_period": 20, "trail_atr_multiplier": 3.0},
        "synthetic_sharpe": 1.95,
        "synthetic_pf": 2.24,
    },
    {
        "run_id": "run_SqueezeBreakout_4h_3878_real",
        "original_run_id": "run_SqueezeBreakout_4h_3878",
        "name": "SqueezeBreakout",
        "tf": "4h",
        "class_path": "src.gold_research.strategies.breakout.squeeze_breakout.SqueezeBreakout",
        "config_class_path": "src.gold_research.strategies.breakout.squeeze_breakout.SqueezeBreakoutConfig",
        "params": {"bb_period": 20, "kc_period": 20, "trail_atr_multiplier": 2.0},
        "synthetic_sharpe": 1.16,
        "synthetic_pf": 1.24,
    },
    {
        "run_id": "run_EMAPullback_4h_9868_real",
        "original_run_id": "run_EMAPullback_4h_9868",
        "name": "EMAPullback",
        "tf": "4h",
        "class_path": "src.gold_research.strategies.pullback.ema_pullback.EMAPullback",
        "config_class_path": "src.gold_research.strategies.pullback.ema_pullback.EMAPullbackConfig",
        "params": {"fast_period": 21, "slow_period": 50, "pullback_tolerance": 0.0005, "trail_atr_multiplier": 1.5},
        "synthetic_sharpe": 1.23,
        "synthetic_pf": 1.42,
    },
    {
        "run_id": "run_Donchian_4h_2698_real",
        "original_run_id": "run_Donchian_4h_2698",
        "name": "Donchian",
        "tf": "4h",
        "class_path": "src.gold_research.strategies.trend.donchian_breakout.DonchianBreakout",
        "config_class_path": "src.gold_research.strategies.trend.donchian_breakout.DonchianBreakoutConfig",
        "params": {"channel_lookback": 50, "trail_atr_multiplier": 2.0},
        "synthetic_sharpe": 1.36,
        "synthetic_pf": 1.53,
    },
    {
        "run_id": "run_BollReversion_5m_8427_real",
        "original_run_id": "run_BollReversion_5m_8427",
        "name": "BollReversion",
        "tf": "5m",
        "class_path": "src.gold_research.strategies.mean_reversion.bollinger_reversion.BollingerReversion",
        "config_class_path": "src.gold_research.strategies.mean_reversion.bollinger_reversion.BollingerReversionConfig",
        "params": {"period": 20, "std_devs": 2.0, "hold_bars": 5},
        "synthetic_sharpe": 1.51,
        "synthetic_pf": 1.68,
    },
    {
        "run_id": "run_ZScoreReversion_15m_8360_real",
        "original_run_id": "run_ZScoreReversion_15m_8360",
        "name": "ZScoreReversion",
        "tf": "15m",
        "class_path": "src.gold_research.strategies.mean_reversion.zscore_reversion.ZScoreReversion",
        "config_class_path": "src.gold_research.strategies.mean_reversion.zscore_reversion.ZScoreReversionConfig",
        "params": {"period": 30, "z_threshold": 2.0, "trail_atr_multiplier": 1.5},
        "synthetic_sharpe": 1.79,
        "synthetic_pf": 1.87,
    },
]

# ===========================================================================
# TRACKER
# ===========================================================================
TRACKER_PATH = ProjectPaths.RESULTS / "sprint_04_tracker.json"
RESULTS_DIR = ProjectPaths.RESULTS / "raw_runs" / "SPRINT_04_REAL"

def init_tracker():
    """Create or load the sprint tracker."""
    if TRACKER_PATH.exists():
        with open(TRACKER_PATH) as f:
            return json.load(f)
    
    tracker = {
        "sprint": "04",
        "status": "in_progress",
        "started_at": datetime.now().isoformat(),
        "data_source": "real_ibkr",
        "tests": []
    }
    for s in STRATEGIES:
        tracker["tests"].append({
            "run_id": s["run_id"],
            "original_run_id": s["original_run_id"],
            "strategy": s["name"],
            "timeframe": s["tf"],
            "status": "pending",
            "synthetic_sharpe": s["synthetic_sharpe"],
            "real_sharpe": None,
            "synthetic_pf": s["synthetic_pf"],
            "real_pf": None,
            "real_trades": None,
            "verdict": None,
        })
    save_tracker(tracker)
    return tracker

def save_tracker(tracker):
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, "w") as f:
        json.dump(tracker, f, indent=4)

def update_tracker(tracker, run_id, **kwargs):
    for test in tracker["tests"]:
        if test["run_id"] == run_id:
            test.update(kwargs)
            break
    save_tracker(tracker)

# ===========================================================================
# ENGINE HELPERS
# ===========================================================================
def create_engine():
    """Create a clean BacktestEngine."""
    config = BacktestEngineConfig(
        trader_id="BACKTESTER-001",
        logging=LoggingConfig(log_level="ERROR")
    )
    engine = BacktestEngine(config=config)
    
    venue = Venue("IDEALPRO")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=None,
        starting_balances=[Money.from_str("100000 USD")]
    )
    return engine

def add_xauusd_instrument(engine):
    """Add the XAUUSD instrument definition."""
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
        ts_init=0
    )
    engine.add_instrument(instrument)
    return instrument

def load_strategy_and_config(strat_def):
    """Dynamically load the strategy class and its config class."""
    import importlib
    
    # Load config class
    config_module_path, config_class_name = strat_def["config_class_path"].rsplit(".", 1)
    config_module = importlib.import_module(config_module_path)
    ConfigClass = getattr(config_module, config_class_name)
    
    # Load strategy class
    strat_module_path, strat_class_name = strat_def["class_path"].rsplit(".", 1)
    strat_module = importlib.import_module(strat_module_path)
    StrategyClass = getattr(strat_module, strat_class_name)
    
    return StrategyClass, ConfigClass

def extract_results(engine, run_id):
    """Extract equity curve and trade log from the completed engine."""
    # Get account events / reports
    try:
        reports = engine.trader.generate_order_fills_report()
    except Exception:
        reports = pd.DataFrame()
    
    try:
        account_report = engine.trader.generate_account_report(Venue("IDEALPRO"))
    except Exception:
        account_report = pd.DataFrame()
    
    try:
        positions_report = engine.trader.generate_positions_report()
    except Exception:
        positions_report = pd.DataFrame()
    
    return {
        "fills": reports,
        "account": account_report,
        "positions": positions_report,
    }

def build_scorecard_from_engine(engine, run_id):
    """Build a real scorecard from engine results."""
    
    # Try to get position data
    try:
        positions_report = engine.trader.generate_positions_report()
    except Exception:
        positions_report = pd.DataFrame()
    
    # Try to get fills for equity construction  
    try:
        fills_report = engine.trader.generate_order_fills_report()
    except Exception:
        fills_report = pd.DataFrame()
    
    # Get all account balances
    try:
        account_report = engine.trader.generate_account_report(Venue("IDEALPRO"))
    except Exception:
        account_report = pd.DataFrame()
    
    total_trades = 0
    win_rate = 0.0
    profit_factor = 0.0
    net_profit = 0.0
    sharpe = 0.0
    sortino_val = 0.0
    calmar_val = 0.0
    mdd = 0.0
    status = "COMPLETED"
    
    if not positions_report.empty and "realized_pnl" in positions_report.columns:
        # Calculate from positions (Nautilus returns PnL as 'X.XX USD' strings)
        pnl_col = positions_report["realized_pnl"].apply(
            lambda x: float(str(x).replace(" USD", "").replace(",", "")) if pd.notna(x) else 0.0
        )
        total_trades = len(pnl_col)
        winners = pnl_col[pnl_col > 0]
        losers = pnl_col[pnl_col <= 0]
        
        win_rate = len(winners) / total_trades if total_trades > 0 else 0.0
        gross_profit = float(winners.sum()) if len(winners) > 0 else 0.0
        gross_loss = abs(float(losers.sum())) if len(losers) > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
        net_profit = gross_profit - gross_loss
        
        # Build mock equity curve from cumulative PnL
        equity = 100000.0 + pnl_col.cumsum()
        equity_series = pd.Series(equity.values, dtype=float)
        
        if len(equity_series) > 1:
            returns = equity_series.pct_change().dropna()
            sharpe = sharpe_ratio(returns)
            sortino_val = sortino_ratio(returns)
            mdd = max_drawdown(equity_series)
            calmar_val = calmar_ratio(returns, equity_series)
    elif not fills_report.empty:
        total_trades = len(fills_report) // 2  # approximate: 2 fills per round-trip
        status = "COMPLETED_LIMITED_DATA"
    else:
        status = "NO_TRADES"
    
    return StrategyScorecard(
        run_id=run_id,
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=min(profit_factor, 999.99),  # cap inf
        total_net_profit=net_profit,
        sharpe=sharpe,
        sortino=sortino_val,
        calmar=calmar_val,
        max_dd_pct=mdd,
        status=status,
    )

# ===========================================================================
# MAIN EXECUTION
# ===========================================================================
def run_single_strategy(strat_def, tracker):
    """Execute a single strategy against real data."""
    run_id = strat_def["run_id"]
    tf = strat_def["tf"]
    name = strat_def["name"]
    
    logger.info(f"{'='*60}")
    logger.info(f"STARTING: {name} / {tf} ({run_id})")
    logger.info(f"{'='*60}")
    
    update_tracker(tracker, run_id, status="running")
    
    try:
        # 1. Load data
        data_file = TF_TO_FILE[tf]
        logger.info(f"Loading data from {data_file.name}...")
        df = load_ib_parquet(str(data_file))
        
        # Fix volume: IBKR returns -1 for forex
        df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
        
        logger.info(f"Loaded {len(df):,} bars, {df['datetime'].min()} -> {df['datetime'].max()}")
        
        # 2. Convert to Nautilus bars
        logger.info("Converting to Nautilus Bar objects...")
        bars = df_to_nautilus_bars(df, "XAUUSD", "IDEALPRO", tf)
        logger.info(f"Created {len(bars):,} Nautilus Bar objects")
        
        # 3. Create engine
        engine = create_engine()
        instrument = add_xauusd_instrument(engine)
        
        # 4. Add bars to engine
        engine.add_data(bars)
        
        # 5. Instantiate strategy
        StrategyClass, ConfigClass = load_strategy_and_config(strat_def)
        config = ConfigClass(
            instrument_id="XAUUSD-IDEALPRO-USD",
            timeframe=tf,
            **strat_def["params"]
        )
        strategy = StrategyClass(config=config)
        engine.add_strategy(strategy)
        
        # 6. Run!
        logger.info("Running backtest engine...")
        engine.run()
        logger.info("Engine completed.")
        
        # 7. Build scorecard
        scorecard = build_scorecard_from_engine(engine, run_id)
        
        # 8. Save results
        run_dir = RESULTS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Save scorecard
        with open(run_dir / "scorecard.json", "w") as f:
            json.dump(scorecard.model_dump(), f, indent=4)
        
        # Save spec
        spec = {
            "experiment_id": "SPRINT_04_REAL",
            "run_id": run_id,
            "strategy": name,
            "timeframe": tf,
            "params": strat_def["params"],
            "data_source": str(data_file),
            "data_rows": len(df),
            "data_range": f"{df['datetime'].min()} -> {df['datetime'].max()}",
        }
        with open(run_dir / "spec.json", "w") as f:
            json.dump(spec, f, indent=4, default=str)
        
        # Save reports
        results = extract_results(engine, run_id)
        for report_name, report_df in results.items():
            if isinstance(report_df, pd.DataFrame) and not report_df.empty:
                report_df.to_csv(run_dir / f"{report_name}.csv", index=True)
        
        # 9. Update tracker
        update_tracker(tracker, run_id,
            status="completed",
            real_sharpe=round(scorecard.sharpe, 4),
            real_pf=round(scorecard.profit_factor, 4),
            real_trades=scorecard.total_trades,
            real_net_profit=round(scorecard.total_net_profit, 2),
            real_max_dd=round(scorecard.max_dd_pct, 4),
            verdict="PASS" if scorecard.sharpe > 0.5 and scorecard.profit_factor > 1.0 else "FAIL",
        )
        
        logger.info(f"RESULT: Sharpe={scorecard.sharpe:.4f}, PF={scorecard.profit_factor:.4f}, "
                     f"Trades={scorecard.total_trades}, NetPnL=${scorecard.total_net_profit:,.2f}")
        
        # Clean up engine
        engine.dispose()
        
        return scorecard
        
    except Exception as e:
        logger.error(f"FAILED: {name}/{tf} - {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        update_tracker(tracker, run_id, status="failed", verdict=f"ERROR: {str(e)[:100]}")
        return None


def main():
    logger.info("=" * 70)
    logger.info("SPRINT 04: REAL DATA VALIDATION")
    logger.info("=" * 70)
    
    tracker = init_tracker()
    
    results = []
    for strat_def in STRATEGIES:
        run_id = strat_def["run_id"]
        
        # Check if already completed
        for test in tracker["tests"]:
            if test["run_id"] == run_id and test["status"] == "completed":
                logger.info(f"SKIPPING {run_id} (already completed)")
                break
        else:
            scorecard = run_single_strategy(strat_def, tracker)
            if scorecard:
                results.append((strat_def, scorecard))
    
    # Final summary
    logger.info("\n" + "=" * 70)
    logger.info("SPRINT 04 RESULTS SUMMARY")
    logger.info("=" * 70)
    
    # Reload tracker for final state
    with open(TRACKER_PATH) as f:
        tracker = json.load(f)
    
    completed = [t for t in tracker["tests"] if t["status"] == "completed"]
    failed = [t for t in tracker["tests"] if t["status"] == "failed"]
    
    logger.info(f"Completed: {len(completed)}/{len(STRATEGIES)}")
    logger.info(f"Failed: {len(failed)}/{len(STRATEGIES)}")
    
    if completed:
        logger.info(f"\n{'Strategy':<25} {'TF':<5} {'Synth Sharpe':>12} {'Real Sharpe':>12} {'Synth PF':>10} {'Real PF':>10} {'Trades':>8} {'Verdict':>8}")
        logger.info("-" * 90)
        for t in completed:
            real_sharpe = t.get("real_sharpe", 0) or 0
            real_pf = t.get("real_pf", 0) or 0
            logger.info(
                f"{t['strategy']:<25} {t['timeframe']:<5} "
                f"{t['synthetic_sharpe']:>12.4f} {real_sharpe:>12.4f} "
                f"{t['synthetic_pf']:>10.4f} {real_pf:>10.4f} "
                f"{t.get('real_trades', 0):>8} {t.get('verdict', 'N/A'):>8}"
            )
    
    # Update tracker status
    if len(completed) + len(failed) == len(STRATEGIES):
        tracker["status"] = "complete"
        tracker["completed_at"] = datetime.now().isoformat()
        save_tracker(tracker)
    
    logger.info(f"\nTracker saved to: {TRACKER_PATH}")
    logger.info(f"Run artifacts at: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
