"""
Time Series Validity Checks.

Ensures timestamps are localized correctly to UTC, strictly monotonic 
(increasing), and free of duplicates.
"""
import pandas as pd
from typing import Dict, Any, Tuple

def check_time_consistency(df: pd.DataFrame) -> Tuple[bool, Dict[str, Any]]:
    """
    Validates time attributes of the dataframe.
    
    Checks:
    1. Timezone is strictly UTC.
    2. Zero duplicates.
    3. Strictly monotonic increasing timestamps.
    
    Args:
        df: Pandas Dataframe with 'datetime' index or column.
        
    Returns:
        (is_valid, report_dictionary)
    """
    report = {
        "passed": True,
        "is_utc": False,
        "duplicate_count": 0,
        "is_monotonic": False,
        "total_rows": len(df)
    }
    
    if "datetime" not in df.columns or df.empty:
        report["passed"] = False
        report["error"] = "Missing datetime column or empty dataframe."
        return False, report
        
    times = df["datetime"]
    
    # Check Timezone
    if hasattr(times.dtype, "tz") and str(times.dt.tz) == "UTC":
        report["is_utc"] = True
    else:
        report["passed"] = False

    # Check Duplicates
    dup_count = int(times.duplicated().sum())
    report["duplicate_count"] = dup_count
    if dup_count > 0:
        report["passed"] = False
        
    # Check Monotonicity
    is_mono = bool(times.is_monotonic_increasing)
    report["is_monotonic"] = is_mono
    if not is_mono:
        report["passed"] = False
        
    return report["passed"], report
