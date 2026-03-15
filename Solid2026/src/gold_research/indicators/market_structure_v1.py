import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

def get_data(symbol, timeframe, count=500):
    """
    Fetch OHLCV data from MT5.
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def detect_structures(df, tf_name, length=5):
    """
    Detect BOS and CHoCH based on fractal logic from Pine script.
    """
    if df.empty:
        return []

    p = length // 2
    n = len(df)
    
    # Pre-calculate sign sums for fractal detection
    # Pine: dh = math.sum(math.sign(high - high[1]), p)
    high_diff_sign = np.sign(df['high'].diff())
    low_diff_sign = np.sign(df['low'].diff())
    
    dh = high_diff_sign.rolling(p).sum()
    dl = low_diff_sign.rolling(p).sum()
    
    # State variables
    upper_value = None
    upper_loc = None
    upper_iscrossed = True # Start true so we wait for first fractal
    
    lower_value = None
    lower_loc = None
    lower_iscrossed = True # Start true so we wait for first fractal
    
    os = 0 # 1 for bullish trend, -1 for bearish trend
    structures = []

    for i in range(length, n):
        # Current bar index n in Pine is i
        # Fractals are detected p bars ago
        
        # Bullish Fractal (Pivot High)
        # Pine: bullf = dh == -p and dh[p] == p and high[p] == ta.highest(length)
        # dh[i] is sum of signs from i-p+1 to i
        # dh[i-p] is sum of signs from i-2p+1 to i-p
        
        bullf = False
        if i >= 2*p:
            # Check if high[i-p] is a fractal high
            cond1 = dh.iloc[i] == -p
            cond2 = dh.iloc[i-p] == p
            cond3 = df['high'].iloc[i-p] == df['high'].iloc[i-length+1 : i+1].max()
            if cond1 and cond2 and cond3:
                bullf = True
                upper_value = df['high'].iloc[i-p]
                upper_loc = i - p
                upper_iscrossed = False

        # Bearish Fractal (Pivot Low)
        # Pine: bearf = dl == p and dl[p] == -p and low[p] == ta.lowest(length)
        bearf = False
        if i >= 2*p:
            cond1 = dl.iloc[i] == p
            cond2 = dl.iloc[i-p] == -p
            cond3 = df['low'].iloc[i-p] == df['low'].iloc[i-length+1 : i+1].min()
            if cond1 and cond2 and cond3:
                bearf = True
                lower_value = df['low'].iloc[i-p]
                lower_loc = i - p
                lower_iscrossed = False

        # Check for Bullish Structure Break (ta.crossover: close crosses above level)
        if upper_value is not None and not upper_iscrossed:
            prev_close = df['close'].iloc[i-1] if i > 0 else 0
            if df['close'].iloc[i] > upper_value and prev_close <= upper_value:
                structure_type = "CHoCH" if os == -1 else "BOS"
                structures.append({
                    'type': structure_type,
                    'direction': 'Bullish',
                    'price': float(upper_value),
                    'time': df['time'].iloc[i],
                    'timeframe': tf_name,
                    'bar_index': i
                })
                upper_iscrossed = True
                os = 1

        # Check for Bearish Structure Break (ta.crossunder: close crosses below level)
        if lower_value is not None and not lower_iscrossed:
            prev_close = df['close'].iloc[i-1] if i > 0 else float('inf')
            if df['close'].iloc[i] < lower_value and prev_close >= lower_value:
                structure_type = "CHoCH" if os == 1 else "BOS"
                structures.append({
                    'type': structure_type,
                    'direction': 'Bearish',
                    'price': float(lower_value),
                    'time': df['time'].iloc[i],
                    'timeframe': tf_name,
                    'bar_index': i
                })
                lower_iscrossed = True
                os = -1

    return structures

def main():
    if not mt5.initialize():
        print("MT5 initialize failed")
        return

    symbol = "XAUUSD"
    timeframes = {
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1
    }

    print(f"Market Structure Analysis for {symbol} - {datetime.now()}")
    print("-" * 60)

    for tf_name, tf_val in timeframes.items():
        df = get_data(symbol, tf_val, 500)
        if df.empty:
            print(f"No data for {tf_name}")
            continue
        
        structures = detect_structures(df, tf_name)
        
        print(f"\nTimeframe: {tf_name}")
        if not structures:
            print("  No structures detected in last 500 bars.")
        else:
            # Print last 5 structures
            for s in structures[-5:]:
                print(f"  {s['time']} | {s['type']} {s['direction']} at {s['price']:.2f}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
