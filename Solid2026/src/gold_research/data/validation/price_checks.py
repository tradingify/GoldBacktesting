"""
Pricing Logic Validity Checks.

Ensures OHLC structure is physically possible (e.g. Low <= High)
and flags suspicious spikes indicative of bad ticks or data feed errors.
"""
import pandas as pd
from typing import Dict, Any, Tuple

def check_price_logic(df: pd.DataFrame, max_spike_pct: float = 0.10) -> Tuple[bool, Dict[str, Any]]:
    """
    Validates financial logic of OHLC pricing and detects severe anomalies.
    
    Checks:
    1. No negative prices.
    2. Low <= Open/Close <= High.
    3. Low > 0 format constraint.
    4. Identifies abnormal Bar-to-Bar spikes > max_spike_pct.
    
    Args:
        df: Candlestick dataframe.
        max_spike_pct: Float percentage threshold (e.g., 0.10 = 10%) for spike detection.
        
    Returns:
        (is_valid, report_dictionary)
    """
    report = {
        "passed": True,
        "negative_prices_count": 0,
        "illogical_ohlc_count": 0,
        "suspicious_spikes_count": 0
    }
    
    if df.empty:
        report["passed"] = False
        report["error"] = "Empty dataframe."
        return False, report
        
    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            report["passed"] = False
            report["error"] = f"Missing {col}."
            return False, report

    # 1. Negative Prices
    neg_mask = (df["open"] < 0) | (df["high"] < 0) | (df["low"] < 0) | (df["close"] < 0)
    neg_count = int(neg_mask.sum())
    report["negative_prices_count"] = neg_count
    if neg_count > 0:
        report["passed"] = False

    # 2. Illogical OHLC bounds (Low > High, Low > Open, etc)
    logic_mask = (df["low"] > df["high"]) | (df["low"] > df["open"]) | (df["low"] > df["close"]) | \
                 (df["high"] < df["open"]) | (df["high"] < df["close"])
    logic_error_count = int(logic_mask.sum())
    report["illogical_ohlc_count"] = logic_error_count
    if logic_error_count > 0:
        report["passed"] = False

    # 3. Spikes (Bar to Bar High/Low differences > threshold)
    if len(df) > 1:
        # Pct change based on previous close vs current High/Low extremes
        pct_high = (df["high"] / df["close"].shift(1)) - 1
        pct_low = (df["low"] / df["close"].shift(1)) - 1
        
        spike_mask = (pct_high.abs() > max_spike_pct) | (pct_low.abs() > max_spike_pct)
        # ignore first row since prior close is NaN
        spike_count = int(spike_mask.sum())
        report["suspicious_spikes_count"] = spike_count
        if spike_count > 0:
            report["passed"] = False
            
    return report["passed"], report
