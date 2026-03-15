"""
IBKR Parquet Data Loader

Parses raw data exported from Interactive Brokers, specifically handling
the inconsistent datetime string formats and standardizing them to UTC.
"""
import pandas as pd
from pathlib import Path
from typing import Union
import re
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.logging import logger

def _parse_datetime(dt_str: str) -> pd.Timestamp:
    """
    Parse any of the datetime formats present in the IBKR source files.
    
    Args:
        dt_str: String representation of the datetime.
        
    Returns:
        pd.Timestamp localized to UTC.
    """
    if isinstance(dt_str, pd.Timestamp):
        return dt_str.tz_convert("UTC") if dt_str.tzinfo is not None else dt_str.tz_localize("UTC")

    s = str(dt_str).strip()

    # Format: '20250225 18:00:00 US/Eastern'
    m = re.match(r"^(\d{8})\s+(\d{2}:\d{2}:\d{2})\s+(\S+)$", s)
    if m:
        date_part, time_part, tz = m.groups()
        ts = pd.Timestamp(f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part}", tz=tz)
        return ts.tz_convert("UTC")

    # Format: '20250227  15:00:00' (double space, no tz → treat as UTC)
    m = re.match(r"^(\d{8})\s+(\d{2}:\d{2}:\d{2})$", s)
    if m:
        date_part, time_part = m.groups()
        return pd.Timestamp(f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part}", tz="UTC")

    # Format: '20240304' (date only → midnight UTC)
    m = re.match(r"^(\d{8})$", s)
    if m:
        d = m.group(1)
        return pd.Timestamp(f"{d[:4]}-{d[4:6]}-{d[6:8]}", tz="UTC")

    raise ValueError(f"Unrecognised datetime format: {repr(dt_str)}")

def load_ib_parquet(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    Loads raw parquet files dumped from IBKR and parses missing timezone info.
    
    Args:
        filepath: Path to the raw IBKR parquet file.
        
    Returns:
        DataFrame with standardized UTC datetime column.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        logger.error(f"Failed to find raw data file: {filepath}")
        raise FileNotFoundError(f"Parquet file not found at {filepath}")
        
    logger.info(f"Loading raw dataset from {filepath.name}...")
    df = pd.read_parquet(filepath)
    if df.empty:
        logger.warning(f"File {filepath} is empty.")
        return df
         
    # Parse datetimes
    df["datetime"] = df["datetime"].apply(_parse_datetime)
    logger.info(f"Successfully loaded {len(df)} rows.")
    return df
