"""
Nautilus Bar Constructor

Converts cleaned, validated pandas dataframes into the internal Event structures
(`Bar`) required by the Nautilus Trader Backtest engine.
"""
import pandas as pd
from typing import List
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity

# Maps shorthand timeframe strings -> (step size, BarAggregation enum)
TIMEFRAME_MAP = {
    "1m":   (1, BarAggregation.MINUTE),
    "5m":   (5, BarAggregation.MINUTE),
    "15m":  (15, BarAggregation.MINUTE),
    "30m":  (30, BarAggregation.MINUTE),
    "1h":   (1, BarAggregation.HOUR),
    "4h":   (4, BarAggregation.HOUR),
    "1d":   (1, BarAggregation.DAY),
}

def df_to_nautilus_bars(df: pd.DataFrame, instrument: str, venue: str, timeframe: str, price_precision: int = 2) -> List[Bar]:
    """
    Converts a normalized Pandas DataFrame into a list of Nautilus Bar objects.
    
    Args:
        df: Normalized dataframe with [datetime, open, high, low, close, volume] columns.
        instrument: Specific instrument ticker (e.g., 'XAUUSD').
        venue: Venue identifier string (e.g., 'SIM' or 'IDEALPRO').
        timeframe: The aggregation timeframe key (e.g., '1h').
        
    Returns:
        List of initialized, internally consistent Nautilus Bar objects.
        
    Raises:
        ValueError: if the timeframe mapping isn't defined in TIMEFRAME_MAP.
    """
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Must be one of {list(TIMEFRAME_MAP.keys())}")
        
    step, aggregation = TIMEFRAME_MAP[timeframe]
    instrument_id = InstrumentId(Symbol(instrument), Venue(venue))
    bar_spec = BarSpecification(step, aggregation, PriceType.LAST)
    bar_type = BarType(instrument_id, bar_spec, AggregationSource.EXTERNAL)
    
    bars: List[Bar] = []
    
    # Usually fast enough for initial loads up to a few million rows.
    # High precision ensures exact matching with the SIM backend's 5 decimals rule for XAUUSD.
    for _, row in df.iterrows():
        ts_ns = int(row["datetime"].value)
        vol = max(0, int(row["volume"])) if pd.notna(row["volume"]) else 0
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price(row["open"], price_precision),
                high=Price(row["high"], price_precision),
                low=Price(row["low"], price_precision),
                close=Price(row["close"], price_precision),
                volume=Quantity.from_int(vol),
                ts_event=ts_ns,
                ts_init=ts_ns
            )
        )
        
    return bars
