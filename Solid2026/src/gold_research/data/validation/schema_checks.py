"""
Schema Validation Module.

Ensures that processed dataframes structurally comply with 
downstream strategy expectations before analysis begins.
"""
import pandas as pd
from typing import Dict, Any, Tuple

def check_schema_compliance(df: pd.DataFrame) -> Tuple[bool, Dict[str, Any]]:
    """
    Validates that the required columns are present and free of NaNs.
    
    Args:
        df: Processed dataframe to validate.
        
    Returns:
        (is_valid, report_dictionary)
    """
    report = {
        "passed": True,
        "missing_columns": [],
        "nan_counts": {}
    }
    
    if df.empty:
        report["passed"] = False
        report["error"] = "Dataframe is empty."
        return False, report
        
    required_cols = {"datetime", "open", "high", "low", "close", "volume"}
    missing = list(required_cols - set(df.columns))
    
    if missing:
        report["passed"] = False
        report["missing_columns"] = missing
        
    for col in required_cols:
        if col in df.columns:
            nan_count = int(df[col].isna().sum())
            if nan_count > 0:
                report["passed"] = False
                report["nan_counts"][col] = nan_count
                
    return report["passed"], report
