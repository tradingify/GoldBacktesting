"""
Sprint 06: Isolated Indicator Testing
=====================================
Runs a purely isolated indicator test (Liquidity Pools) over 1 month of data
to debug visibility and trade execution mapping.
"""
import sys
import json
import logging
import traceback
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")

from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.data.ingest.bar_builder import df_to_nautilus_bars
from src.gold_research.analytics.scorecards import StrategyScorecard
from src.gold_research.analytics.metrics import sharpe_ratio, max_drawdown
from src.gold_research.core.paths import ProjectPaths

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.objects import Price, Quantity, Money, Currency
from nautilus_trader.config import LoggingConfig
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("sprint_06_isolated")

REAL_DATA_DIR = Path(r"D:\.openclaw\GoldBacktesting\bars")

def create_engine():
    config = BacktestEngineConfig(trader_id="BACKTESTER-001", logging=LoggingConfig(log_level="INFO"))
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

def build_scorecard(engine, run_id):
    # Summary provided by engine metrics is usually most reliable
    # But for our custom scorecard, we'll try to get the full report
    try:
        # Use positions() to get both open and closed if needed
        # but generate_positions_report is for closed (trades)
        pos_report = engine.trader.generate_positions_report()
    except Exception as e:
        logger.error(f"Failed to generate positions report: {e}")
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


TF_TO_FILE = {
    "15m": REAL_DATA_DIR / "xauusd_15_mins.parquet",
    "1h":  REAL_DATA_DIR / "xauusd_1_hour.parquet",
}

def run_isolated_1_month(tf="15m"):
    logger.info(f"Running Isolated Liquidity Pools on {tf} (Past 1 Month)")
    
    df = load_ib_parquet(str(TF_TO_FILE[tf]))
    
    # Ensure there's a proper datetime column before applying cutoff
    if "date" in df.columns and pd.api.types.is_string_dtype(df["date"]):
        df["datetime"] = pd.to_datetime(df["date"])
    elif "datetime" not in df.columns:
        df["datetime"] = pd.to_datetime(df.index)

    df.set_index("datetime", inplace=False) # Keep datetime as a column for bar_builder but sort by it

    # Filter to exactly 1 month of data.
    cutoff_time = df["datetime"].iloc[-1] - pd.Timedelta(days=30)
    df = df[df["datetime"] >= cutoff_time]
    
    df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
    logger.info(f"Filtered {tf} data to 1 month: {len(df)} bars from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")

    bars = df_to_nautilus_bars(df, "XAUUSD", "IDEALPRO", tf)
    
    engine = create_engine()
    add_xauusd_instrument(engine)
    engine.add_data(bars)
    
    from src.gold_research.strategies.smc.confluence_scorer_strategy import ConfluenceScorerStrategy, ConfluenceScorerConfig
    
    cfg = ConfluenceScorerConfig(
        instrument_id="XAUUSD-IDEALPRO-USD", 
        timeframe=tf,
        window_size=200,
        stop_atr_multiplier=1.5,
        trailing_stop_multiplier=1.5,
        active_detectors=("liquidity_pools",),
        min_fire_score=1  # A sweep alone triggers entry
    )
    
    engine.add_strategy(ConfluenceScorerStrategy(config=cfg))
    engine.run()
    
    sc = build_scorecard(engine, f"isolated_liq_{tf}")
    logger.info(f"-> Trades: {sc.total_trades:>3}, PF: {sc.profit_factor:>6.2f}, Sharpe: {sc.sharpe:>6.2f}, PnL: ${sc.total_net_profit:>10,.2f}")
    engine.dispose()
    return sc

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("STARTING SPRINT 06 ISOLATED 1-MONTH RUN")
    logger.info("=" * 80)
    run_isolated_1_month("15m")
    run_isolated_1_month("1h")
