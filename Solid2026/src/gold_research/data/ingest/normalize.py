"""
Data Normalization Module

Enforces schema contracts on raw ingested data, ensuring
that downstream components (like Nautilus) receive clean, validated OHLCV.
"""
import pandas as pd
from src.gold_research.core.logging import logger

def normalize_candles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizes a dataframe of OHLCV to standard schema.
    
    1. Validates required column presence.
    2. Enforces time sort order.
    3. Handles and reports duplicates.
    4. Enforces strict float typing for OHLC.
    5. Formats volume dynamically based on logic conventions.
    
    Args:
        df: The raw dataframe loaded from source.
        
    Returns:
        Cleaned, ordered dataframe ready for strategy consumption or Bar mapping.
    """
    if df.empty:
        return df
        
    required_cols = ["datetime", "open", "high", "low", "close"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in candle dataframe: {missing}")
        
    # Drop duplicates by exact time
    original_size = len(df)
    df = df.drop_duplicates(subset=["datetime"])
    if len(df) < original_size:
        logger.warning(f"Dropped {original_size - len(df)} duplicate timestamps during normalization.")
        
    # Sort securely
    df = df.sort_values("datetime").reset_index(drop=True)
    
    # Force convert types
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    
    # Hardcode volume to 0 for generic non-vol instruments (like Spot Gold) per Master Plan
    # If standard volume existed, we'd cast it to strict int.
    if "volume" not in df.columns:
        df["volume"] = 0
    else:
        df["volume"] = df["volume"].fillna(0).astype('int64')
        # specific hardoverride applied defensively as IBKR volume logic for spot gold is often -1
        df["volume"] = 0 
    
    logger.info(f"Data normalized successfully: {len(df)} rows remain.")
    return df
