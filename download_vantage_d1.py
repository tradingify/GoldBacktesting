"""
Download D1 bars from Vantage MT5 for XAUUSD
Date range: Feb 2024 - Feb 2026
Store in: D:\.openclaw\GoldBacktesting\BarsVantage\
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time

# Config
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_D1
START_DATE = datetime(2024, 2, 1)
END_DATE = datetime(2026, 2, 28)
OUTPUT_DIR = Path(r"D:\.openclaw\GoldBacktesting\BarsVantage")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("VANTAGE MT5 D1 DATA DOWNLOAD")
print("=" * 60)
print(f"Symbol: {SYMBOL}")
print(f"Range: {START_DATE.date()} to {END_DATE.date()}")
print(f"Output: {OUTPUT_DIR}")
print()

# Connect to MT5
if not mt5.initialize(login=24294484, server="VantageInternational-Demo"):
    print(f"MT5 init failed: {mt5.last_error()}")
    exit(1)

print(f"Connected: {mt5.account_info().login} @ {mt5.account_info().server}")
print()

# Download in chunks (MT5 has limits)
chunk_size = 365  # days per request
current = START_DATE
total_bars = 0

while current < END_DATE:
    chunk_end = min(current + timedelta(days=chunk_size), END_DATE)
    
    print(f"Downloading: {current.date()} to {chunk_end.date()}...", end=" ")
    
    rates = mt5.copy_rates_range(SYMBOL, TIMEFRAME, current, chunk_end)
    
    if rates is None or len(rates) == 0:
        print(f"No data (error: {mt5.last_error()})")
        current = chunk_end
        continue
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Save chunk
    filename = f"{SYMBOL}_D1_{current.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}.csv"
    filepath = OUTPUT_DIR / filename
    df.to_csv(filepath, index=False)
    
    print(f"OK {len(df)} bars saved to {filename}")
    total_bars += len(df)
    
    current = chunk_end
    time.sleep(0.5)  # Rate limit

mt5.shutdown()

print()
print("=" * 60)
print(f"DOWNLOAD COMPLETE")
print(f"Total bars: {total_bars}")
print(f"Files saved to: {OUTPUT_DIR}")
print("=" * 60)
