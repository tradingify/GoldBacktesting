"""
SMC Adapters for Nautilus Trader.

Bridges the gap between sequential Nautilus Bar streams and Pandas DataFrame-based 
ICT/SMC indicators.
"""
from typing import Optional, Dict, Any, List
import pandas as pd

from nautilus_trader.model.data import Bar
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent


class RollingBarWindow:
    """
    Accumulates Nautilus Bar objects into a rolling Pandas DataFrame.
    """
    def __init__(self, window_size: int, timeframe: str = "15m"):
        self.window_size = window_size
        self.timeframe = timeframe
        self._df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        
    def add(self, bar: Bar):
        # Nautilus ts_init is ending timestamp in nanoseconds
        ts = pd.to_datetime(bar.ts_init, unit='ns', utc=True)
        new_row = pd.DataFrame([{
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume) if hasattr(bar, "volume") else 0.0
        }], index=[ts])
        
        if self._df.empty:
            self._df = new_row
        else:
            self._df = pd.concat([self._df, new_row])
            
        if len(self._df) > self.window_size:
            self._df = self._df.iloc[-self.window_size:]
            
    @property
    def is_ready(self) -> bool:
        return len(self._df) >= self.window_size
        
    def to_dataframe(self) -> pd.DataFrame:
        """Returns the rolling window as a Pandas DataFrame indexed by timestamp."""
        return self._df.copy()


class SMCSignalBase(SignalBase):
    """
    Base class for SMC strategies that require DataFrame input.
    Manages a RollingBarWindow automatically.
    """
    def __init__(self, window_size: int = 200, timeframe: str = "15m"):
        self.rolling_window = RollingBarWindow(window_size=window_size, timeframe=timeframe)
        self.timeframe = timeframe
        
    def update_window(self, current_bar: Bar):
        self.rolling_window.add(current_bar)
        
    def generate(self, current_bar: Bar) -> Optional[SignalIntent]:
        # Note: Strategy update_state MUST call update_window() first
        if not self.rolling_window.is_ready:
            return None
            
        df = self.rolling_window.to_dataframe()
        return self._evaluate_dataframe(df, current_bar)
        
    def _evaluate_dataframe(self, df: pd.DataFrame, current_bar: Bar) -> Optional[SignalIntent]:
        """
        To be implemented by SMC strategy subclass.
        Receives the populated DataFrame containing the last N bars up to and including current_bar.
        """
        raise NotImplementedError("SMC subclasses must implement _evaluate_dataframe")
