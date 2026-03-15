"""
CLI Entrypoint for Data Ingestion.

Discovers raw IB parquet files, passes them through the normalizer,
and saves validated datasets to the processed directory for the core engine.
"""
import argparse
import sys
from pathlib import Path

from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.logging import logger
from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.data.ingest.normalize import normalize_candles

def main():
    parser = argparse.ArgumentParser(description="Ingests and normalizes gold data from IBKR parquets.")
    parser.add_argument("--source-dir", type=str, required=False, help="Explicit override for raw data folder.")
    parser.add_argument("--instrument", type=str, default="gold", help="Instrument string identifier.")
    parser.add_argument("--save", action="store_true", help="If active, dumps clean parquets to parsed processing path.")
    
    args = parser.parse_args()
    
    # 1. Resolve raw directory
    if args.source_dir:
        raw_dir = Path(args.source_dir)
    else:
        raw_dir = ProjectPaths.get_data_raw(instrument=args.instrument)
        
    if not raw_dir.exists() or not list(raw_dir.glob("*.parquet")):
        logger.error(f"No parquet files found in source directory: {raw_dir}")
        sys.exit(1)
        
    out_dir = ProjectPaths.get_data_processed_bars(instrument=args.instrument)
    
    # 2. Ingest and Normalize Process
    processed_count = 0
    for p_file in raw_dir.glob("*.parquet"):
        logger.info(f"Ingesting raw dataset: {p_file.name}")
        
        try:
            # Load and fix UTC
            raw_df = load_ib_parquet(p_file)
            
            # Normalize and sort
            clean_df = normalize_candles(raw_df)
            
            if args.save:
                out_path = out_dir / p_file.name
                clean_df.to_parquet(out_path, index=False)
                logger.info(f"Saved normalized data to -> {out_path}")
            
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Failed to process {p_file.name}. Error: {e}")
            
    logger.info(f"Ingestion CLI complete. Processed {processed_count} files.")

if __name__ == "__main__":
    main()
