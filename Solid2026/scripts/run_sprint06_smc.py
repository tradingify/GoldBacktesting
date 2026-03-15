"""
Sprint 06: SMC Baseline Discovery
=================================
Runs the 3 new SMC strategies against real IBKR bar data to discover baseline performance.
"""
import sys
import json
import logging
import traceback
from pathlib import Path
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")

import pandas as pd

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("sprint_06_smc")

REAL_DATA_DIR = Path(r"D:\.openclaw\GoldBacktesting\bars")
TF_TO_FILE = {
    "15m": REAL_DATA_DIR / "xauusd_15_mins.parquet",
    "1h":  REAL_DATA_DIR / "xauusd_1_hour.parquet",
    "4h":  REAL_DATA_DIR / "xauusd_4_hours.parquet",
}

# 3 New Strategies (excluding 5m for speed on standard SMC run)
STRATEGIES = []
tfs = ["15m", "1h", "4h"]

for tf in tfs:
    STRATEGIES.extend([
        {
            "run_id": f"sprint_06_combo_model_A_{tf}",
            "name": "ComboModelA(FVG+OB+MS)",
            "tf": tf,
            "class_path": "src.gold_research.strategies.smc.confluence_scorer_strategy.ConfluenceScorerStrategy",
            "config_class_path": "src.gold_research.strategies.smc.confluence_scorer_strategy.ConfluenceScorerConfig",
            "params": {
                "active_detectors": ("fvg", "order_blocks", "market_structure"),
                "min_fire_score": 2,
                "window_size": 1000,
                "event_lookback": 50,
                "stop_atr_multiplier": 2.0,
                "trailing_stop_multiplier": 2.0
            }
        },
        {
            "run_id": f"sprint_06_combo_model_B_{tf}",
            "name": "ComboModelB(LiqSweep+MS)",
            "tf": tf,
            "class_path": "src.gold_research.strategies.smc.confluence_scorer_strategy.ConfluenceScorerStrategy",
            "config_class_path": "src.gold_research.strategies.smc.confluence_scorer_strategy.ConfluenceScorerConfig",
            "params": {
                "active_detectors": ("liquidity_pools", "market_structure"),
                "min_fire_score": 2,
                "window_size": 1000,
                "event_lookback": 50,
                "stop_atr_multiplier": 1.5,
                "trailing_stop_multiplier": 1.5
            }
        }
    ])

RESULTS_DIR = ProjectPaths.RESULTS / "raw_runs" / "SPRINT_06_SMC"


def create_engine():
    config = BacktestEngineConfig(trader_id="BACKTESTER-001", logging=LoggingConfig(log_level="ERROR"))
    engine = BacktestEngine(config=config)
    engine.add_venue(
        venue=Venue("IDEALPRO"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=None,
        starting_balances=[Money.from_str("100000 USD")]
    )
    return engine

def add_xauusd_instrument(engine):
    instrument = CurrencyPair(
        instrument_id=InstrumentId(Symbol("XAUUSD"), Venue("IDEALPRO")),
        raw_symbol=Symbol("XAUUSD"),
        base_currency=Currency.from_str("XAU"),
        quote_currency=Currency.from_str("USD"),
        price_precision=2, size_precision=0,
        price_increment=Price(0.01, 2),
        size_increment=Quantity.from_int(1), multiplier=Quantity.from_int(1), lot_size=Quantity.from_int(1),
        max_quantity=Quantity.from_int(1000000), min_quantity=Quantity.from_int(1),
        margin_init=Decimal("0"), margin_maint=Decimal("0"), maker_fee=Decimal("0"), taker_fee=Decimal("0"),
        ts_event=0, ts_init=0
    )
    engine.add_instrument(instrument)

def load_strategy_and_config(strat_def):
    import importlib
    c_mod, c_cls = strat_def["config_class_path"].rsplit(".", 1)
    s_mod, s_cls = strat_def["class_path"].rsplit(".", 1)
    return getattr(importlib.import_module(s_mod), s_cls), getattr(importlib.import_module(c_mod), c_cls)

def build_scorecard(engine, run_id):
    try:
        # Use positions() to get both open and closed if needed
        # but generate_positions_report is for closed (trades)
        pos_report = engine.trader.generate_positions_report()
    except Exception as e:
        logger.error(f"Failed to generate positions report for {run_id}: {e}")
        pos_report = pd.DataFrame()
    
    total_trades = 0
    pnl, pf, sharpe, md = 0.0, 0.0, 0.0, 0.0
    status = "NO_TRADES"
    
    if not pos_report.empty:
        # Nautilus columns might vary by version, often 'realized_pnl' or 'pnl'
        col = "realized_pnl" if "realized_pnl" in pos_report.columns else ("pnl" if "pnl" in pos_report.columns else None)
        if col:
            pnl_series = pos_report[col].apply(lambda x: float(str(x).split(' ')[0].replace(",", "")) if pd.notna(x) else 0.0)
            total_trades = len(pnl_series)
            win, loss = pnl_series[pnl_series > 0], pnl_series[pnl_series <= 0]
            gw, gl = float(win.sum()) if len(win)>0 else 0.0, abs(float(loss.sum())) if len(loss)>0 else 0.0
            pf = gw / gl if gl > 0 else (999.9 if gw > 0 else 0.0)
            pnl = gw - gl
            status = "COMPLETED"
            if len(pnl_series) > 0:
                eq = 100000.0 + pnl_series.cumsum()
                if len(eq) > 1:
                    rets = pd.Series(eq.values).pct_change().dropna()
                    if len(rets) > 0 and rets.std() > 0:
                        sharpe = sharpe_ratio(rets)
                    md = max_drawdown(pd.Series(eq.values))
            
    return StrategyScorecard(run_id=run_id, total_trades=total_trades, win_rate=0.0, profit_factor=pf, total_net_profit=pnl, sharpe=sharpe, sortino=0.0, calmar=0.0, max_dd_pct=md, status=status)


def run_single(strat_def):
    logger.info(f"Running {strat_def['name']} / {strat_def['tf']}...")
    try:
        df = load_ib_parquet(str(TF_TO_FILE[strat_def["tf"]]))
        df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
        bars = df_to_nautilus_bars(df, "XAUUSD", "IDEALPRO", strat_def["tf"])
        engine = create_engine()
        add_xauusd_instrument(engine)
        engine.add_data(bars)
        
        StrategyClass, ConfigClass = load_strategy_and_config(strat_def)
        cfg = ConfigClass(instrument_id="XAUUSD-IDEALPRO-USD", timeframe=strat_def["tf"], **strat_def["params"])
        engine.add_strategy(StrategyClass(config=cfg))
        engine.run()
        
        sc = build_scorecard(engine, strat_def["run_id"])
        
        # Save results
        run_dir = RESULTS_DIR / strat_def["run_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "scorecard.json", "w") as f:
            json.dump(sc.model_dump(), f, indent=4)
            
        logger.info(f"-> Trades: {sc.total_trades:>3}, PF: {sc.profit_factor:>6.2f}, Sharpe: {sc.sharpe:>6.2f}, PnL: ${sc.total_net_profit:>10,.2f}")
        engine.dispose()
        return sc
    except Exception as e:
        logger.error(f"-> Failed: {e}")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    
    logger.info("=" * 80)
    logger.info("STARTING SPRINT 06 SMC BASELINE RUN")
    logger.info("=" * 80)
    
    for s in STRATEGIES:
        sc = run_single(s)
        if sc:
            results.append((s, sc))
            
    print("\n" + "="*80)
    print("SPRINT 06 SMC BASELINE RESULTS")
    print("="*80)
    print(f"{'Strategy':<30} {'TF':<5} {'Trades':>8} {'PF':>8} {'Sharpe':>8} {'PnL':>12}")
    print("-" * 80)
    for s, sc in results:
        print(f"{s['name']:<30} {s['tf']:<5} {sc.total_trades:>8} {sc.profit_factor:>8.2f} {sc.sharpe:>8.2f} {sc.total_net_profit:>12,.2f}")
