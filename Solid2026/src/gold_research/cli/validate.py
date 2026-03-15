"""
CLI Entrypoint for Dataset Validation.

Loops through normalized parquet files to audit 
their structural and financial integrity via the validation modules.
"""
import argparse
import sys
from pathlib import Path

from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.logging import logger
from src.gold_research.data.validation.quality_report import generate_quality_report
import pandas as pd

def main():
    parser = argparse.ArgumentParser(description="Validates clean gold data and dumps quality reports.")
    parser.add_argument("--source-dir", type=str, required=False, help="Wait for specific normalized data folder.")
    parser.add_argument("--instrument", type=str, default="gold", help="Instrument string identifier.")
    
    args = parser.parse_args()
    
    # 1. Resolve normalized directory
    if args.source_dir:
        clean_dir = Path(args.source_dir)
    else:
        clean_dir = ProjectPaths.get_data_processed_bars(instrument=args.instrument)
        
    if not clean_dir.exists() or not list(clean_dir.glob("*.parquet")):
        logger.error(f"No processed parquet files found in source directory: {clean_dir}")
        sys.exit(1)
        
    reports_dir = ProjectPaths.DATA / "checks" / "quality_reports"
    
    # 2. Validation Loop
    processed_count = 0
    failures = 0
    
    for p_file in clean_dir.glob("*.parquet"):
        logger.info(f"Validating dataset: {p_file.name}")
        
        try:
            df = pd.read_parquet(p_file)
            dataset_name = p_file.stem 
            report_path = reports_dir / f"{dataset_name}_report.json"
            
            passed, _ = generate_quality_report(df, dataset_name, report_path)
            
            if not passed:
                failures += 1
                
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Failed to validate {p_file.name}. Error: {e}")
            failures += 1
            
    if failures > 0:
        logger.error(f"Validation CLI complete. {failures}/{processed_count} datasets FAILED logic checks.")
        sys.exit(1)
    else:
        logger.info(f"Validation CLI complete. All {processed_count} datasets PASSED.")

if __name__ == "__main__":
    main()
