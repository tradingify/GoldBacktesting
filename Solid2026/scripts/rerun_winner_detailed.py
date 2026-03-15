import sys
import json
import logging
from pathlib import Path
from decimal import Decimal
import pandas as pd

sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")

from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.data.ingest.bar_builder import df_to_nautilus_bars
from src.gold_research.analytics.metrics import sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio
from src.gold_research.core.paths import ProjectPaths

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.objects import Price, Quantity, Money, Currency
from nautilus_trader.config import LoggingConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("tearsheet_gen")

# Target Winner: Model B / 4h
STRAT_DEF = {
    "run_id": "sprint_06_combo_model_B_4h",
    "tf": "4h",
    "params": {
        "active_detectors": ("liquidity_pools", "market_structure"),
        "min_fire_score": 2,
        "window_size": 1000,
        "event_lookback": 50,
        "stop_atr_multiplier": 1.5,
        "trailing_stop_multiplier": 1.5
    }
}

DATA_PATH = Path(r"D:\.openclaw\GoldBacktesting\bars\xauusd_4_hours.parquet")
OUTPUT_DIR = ProjectPaths.RESULTS / "raw_runs" / "SPRINT_06_SMC" / "sprint_06_combo_model_B_4h"

def run_backtest():
    logger.info("Re-running ComboModelB 4h for detailed artifact generation...")
    df = load_ib_parquet(str(DATA_PATH))
    df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
    bars = df_to_nautilus_bars(df, "XAUUSD", "IDEALPRO", "4h")
    
    config = BacktestEngineConfig(trader_id="BACKTESTER-001", logging=LoggingConfig(log_level="ERROR"))
    engine = BacktestEngine(config=config)
    engine.add_venue(
        venue=Venue("IDEALPRO"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money.from_str("100000 USD")]
    )
    
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
    engine.add_data(bars)
    
    from src.gold_research.strategies.smc.confluence_scorer_strategy import ConfluenceScorerStrategy, ConfluenceScorerConfig
    cfg = ConfluenceScorerConfig(instrument_id="XAUUSD-IDEALPRO-USD", timeframe="4h", **STRAT_DEF["params"])
    engine.add_strategy(ConfluenceScorerStrategy(config=cfg))
    
    engine.run()
    
    # Export Detailed Artifacts
    fills = engine.trader.generate_fills_report()
    positions = engine.trader.generate_positions_report()
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fills.to_csv(OUTPUT_DIR / "fills.csv", index=False)
    positions.to_csv(OUTPUT_DIR / "positions.csv", index=False)
    
    logger.info(f"Artifacts saved to {OUTPUT_DIR}")
    engine.dispose()

if __name__ == "__main__":
    run_backtest()
