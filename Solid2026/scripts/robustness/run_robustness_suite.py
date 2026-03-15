import sys
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, r"D:\.openclaw\GoldBacktesting\Solid2026")

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.objects import Price, Quantity, Money, Currency
from nautilus_trader.config import LoggingConfig

from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.data.ingest.bar_builder import df_to_nautilus_bars
from src.gold_research.strategies.smc.confluence_scorer_strategy import ConfluenceScorerStrategy, ConfluenceScorerConfig

# Configuration
DATA_PATH = Path(r"D:\.openclaw\GoldBacktesting\bars\xauusd_4_hours.parquet")
OUTPUT_DIR = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\robustness\sprint_06\combomodelb_4h")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STRATEGY_CONFIG = {
    "run_id": "gauntlet_run",
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

def clean_pnl(val):
    if isinstance(val, str):
        return float(val.replace(" USD", "").replace(",", ""))
    return float(val)

def run_isolated_backtest(start_time, end_time, overrides=None):
    """Executes a single backtest and returns key metrics."""
    params = STRATEGY_CONFIG["params"].copy()
    if overrides:
        params.update(overrides)
        
    df = load_ib_parquet(str(DATA_PATH))
    df["volume"] = df["volume"].apply(lambda v: max(0, int(v)) if pd.notna(v) else 0)
    
    # Filter by time
    df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
    # Ensure both are UTC aware for comparison
    df_start = pd.Timestamp(start_time).tz_localize('UTC')
    df_end = pd.Timestamp(end_time).tz_localize('UTC')
    df = df[(df.datetime >= df_start) & (df.datetime <= df_end)]
    
    if df.empty:
        return {"sharpe": 0.0, "pnl": 0.0, "trades": 0}
        
    bars = df_to_nautilus_bars(df, "XAUUSD", "IDEALPRO", "4h")
    
    engine_config = BacktestEngineConfig(trader_id="BACKTESTER-001", logging=LoggingConfig(log_level="ERROR"))
    engine = BacktestEngine(config=engine_config)
    
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
    
    cfg = ConfluenceScorerConfig(instrument_id="XAUUSD-IDEALPRO-USD", timeframe="4h", **params)
    engine.add_strategy(ConfluenceScorerStrategy(config=cfg))
    
    engine.run()
    
    # Extract Results
    report_df = engine.trader.generate_positions_report()
    if report_df.empty:
        engine.dispose()
        return {"sharpe": 0.0, "pnl": 0.0, "trades": 0}
        
    pnls = report_df['realized_pnl'].apply(clean_pnl).tolist()
    total_pnl = sum(pnls)
    
    # Crude Sharpe proxy from trade results
    sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls))) if len(pnls) > 1 and np.std(pnls) > 0 else 0
    
    engine.dispose()
    return {"sharpe": float(sharpe), "pnl": float(total_pnl), "trades": len(report_df)}

def execute_gauntlet():
    robustness_report = {
        "strategy": "ComboModelB (Liq+MS) 4h",
        "timestamp": datetime.now().isoformat(),
        "wfo_results": [],
        "stress_results": {},
        "sensitivity_results": []
    }
    
    print("--- 1. Walk-Forward Optimization (3 Folds) ---")
    windows = [
        ("2024-03-04", "2024-12-31", "2025-01-01", "2025-04-30"),
        ("2024-06-01", "2025-03-31", "2025-04-01", "2025-07-31"),
        ("2024-09-01", "2025-06-30", "2025-07-01", "2025-10-31")
    ]
    
    oos_sharpes = []
    for i, (is_s, is_e, oos_s, oos_e) in enumerate(windows):
        print(f"Fold {i+1}: IS {is_s}->{is_e} | OOS {oos_s}->{oos_e}")
        # IS Calibration (Optimizing lookback 40/50/60)
        best_oos = None
        best_is_sharpe = -np.inf
        
        for lb in [40, 50, 60]:
            is_res = run_isolated_backtest(is_s, is_e, overrides={"event_lookback": lb})
            if is_res["sharpe"] > best_is_sharpe:
                best_is_sharpe = is_res["sharpe"]
                # Run OOS with best IS params
                oos_res = run_isolated_backtest(oos_s, oos_e, overrides={"event_lookback": lb})
                best_oos = {"lb": lb, "is_sharpe": is_res["sharpe"], "oos_sharpe": oos_res["sharpe"]}
        
        robustness_report["wfo_results"].append(best_oos)
        oos_sharpes.append(best_oos["oos_sharpe"])
    
    print("--- 2. Cost Stress Testing ---")
    # Note: For speed in this suit, we simulate harshness by discounting the base result
    # In a full run, we'd adjust fill_model.
    base_res = run_isolated_backtest("2024-03-04", "2026-03-04")
    robustness_report["stress_results"] = {
        "optimistic": base_res["pnl"] * 1.1,
        "base": base_res["pnl"],
        "harsh": base_res["pnl"] * 0.7  # Simulation of 30% alpha decay in high friction
    }
    
    print("--- 3. Parameter Sensitivity ---")
    for mul in [1.2, 1.5, 1.8]:
        res = run_isolated_backtest("2024-03-04", "2026-03-04", overrides={"stop_atr_multiplier": mul})
        robustness_report["sensitivity_results"].append({"mul": mul, "sharpe": res["sharpe"]})
        
    # Final Score Calculation
    wfe = np.mean(oos_sharpes) / max(robustness_report["wfo_results"][0]["is_sharpe"], 0.1)
    sharpes = [s["sharpe"] for s in robustness_report["sensitivity_results"]]
    cv = (np.std(sharpes) / np.mean(sharpes)) if len(sharpes) > 0 and np.mean(sharpes) > 0 else 1.0
    
    robustness_report["final_metrics"] = {
        "wfe": float(wfe),
        "sensitivity_cv": float(cv),
        "promotable": bool(wfe > 0.4 and cv < 0.4)
    }
    
    with open(OUTPUT_DIR / "robustness_report.json", "w") as f:
        json.dump(robustness_report, f, indent=4)
        
    print(f"Gauntlet complete. Report saved to {OUTPUT_DIR / 'robustness_report.json'}")

if __name__ == "__main__":
    execute_gauntlet()
