"""
Data Quality Reporter.

Runs all validation checks on a dataframe and aggregates the results 
into a comprehensive JSON report for auditing and dataset registry.
"""
import json
import pandas as pd
from typing import Dict, Any, Tuple
from pathlib import Path
from datetime import datetime

from src.gold_research.data.validation.schema_checks import check_schema_compliance
from src.gold_research.data.validation.time_checks import check_time_consistency
from src.gold_research.data.validation.price_checks import check_price_logic
from src.gold_research.core.logging import logger

def generate_quality_report(df: pd.DataFrame, dataset_name: str, output_path: Path) -> Tuple[bool, Dict[str, Any]]:
    """
    Executes all data quality layers sequentially and saves a JSON report.
    
    Args:
        df: Dataframe to validate.
        dataset_name: Name of the dataset for the report metadata.
        output_path: Where to save the generated JSON report.
        
    Returns:
        (is_valid_overall, report_dict)
    """
    logger.info(f"Generating quality report for {dataset_name}...")
    
    overall_pass = True
    
    # Run Checks
    schema_pass, schema_details = check_schema_compliance(df)
    time_pass, time_details = check_time_consistency(df)
    price_pass, price_details = check_price_logic(df, max_spike_pct=0.10)
    
    overall_pass = schema_pass and time_pass and price_pass
    
    # Construct Output
    report = {
        "dataset_name": dataset_name,
        "timestamp_generated": datetime.utcnow().isoformat() + "Z",
        "overall_status": "PASS" if overall_pass else "FAIL",
        "rows_analyzed": len(df),
        "module_results": {
            "schema_compliance": {
                "passed": schema_pass,
                "details": schema_details
            },
            "time_consistency": {
                "passed": time_pass,
                "details": time_details
            },
            "price_logic": {
                "passed": price_pass,
                "details": price_details
            }
        }
    }
    
    # Output to File
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)
        
    if overall_pass:
         logger.info(f"Quality check PASS -> Saved report to {output_path.name}")
    else:
         logger.error(f"Quality check FAIL -> Check {output_path.name} for anomalies.")
         
    return overall_pass, report
