"""
Common Indicator Library.

Wraps standardized mathematical indicators (built on numpy/pandas)
into stateful objects that can digest Nautilus Bar streams over time.
"""
import numpy as np
from typing import List

class BaseIndicator:
    """Stateful metric tracker that maintains a rolling window of required size."""
    
    def __init__(self, window: int):
        self.window = window
        self.values: List[float] = []
        
    def add(self, value: float):
        """Pushes a new value into the rolling array."""
        self.values.append(value)
        if len(self.values) > self.window:
            self.values.pop(0)
            
    @property
    def is_ready(self) -> bool:
        """Indicates if enough data is captured to compute."""
        return len(self.values) == self.window

class SimpleMovingAverage(BaseIndicator):
    """Rolling simple arithmetic average."""
    
    @property
    def value(self) -> float:
        if not self.is_ready:
            return 0.0
        return sum(self.values) / self.window

class ExponentialMovingAverage:
    """Stateful EMA."""
    def __init__(self, window: int):
        self.window = window
        self.alpha = 2.0 / (window + 1.0)
        self.value = None
        self.count = 0
        
    def add(self, value: float):
        if self.value is None:
            self.value = value
        else:
            self.value = (value * self.alpha) + (self.value * (1.0 - self.alpha))
        self.count += 1
        
    @property
    def is_ready(self) -> bool:
        return self.count >= self.window

class TrueRange(BaseIndicator):
    """Calculates True Range given OHLC tuples."""
    
    def __init__(self, window: int):
        super().__init__(window)
        self.prev_close = None
        
    def add_bar(self, high: float, low: float, close: float):
        if self.prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
            
        self.prev_close = close
        self.add(tr)
        
    @property
    def atr(self) -> float:
        if not self.is_ready:
            return 0.0
        return sum(self.values) / self.window

class DonchianChannel:
    """Tracks Highest High and Lowest Low over a window.
    
    IMPORTANT: upper/lower return the channel from the PREVIOUS window
    (excluding the current bar), so breakout detection works correctly.
    If the current bar's high is included, close > upper is impossible
    since close <= high <= max(highs).
    """
    def __init__(self, window: int):
        self.window = window
        self.highs: List[float] = []
        self.lows: List[float] = []
        # Store previous-bar channel levels for signal comparison
        self._prev_upper: float = 0.0
        self._prev_lower: float = float('inf')
        
    def add_bar(self, high: float, low: float):
        # Snapshot the channel BEFORE adding the new bar
        if len(self.highs) == self.window:
            self._prev_upper = max(self.highs)
            self._prev_lower = min(self.lows)
        
        self.highs.append(high)
        self.lows.append(low)
        if len(self.highs) > self.window:
            self.highs.pop(0)
            self.lows.pop(0)
            
    @property
    def is_ready(self) -> bool:
        return len(self.highs) == self.window and self._prev_upper > 0
        
    @property
    def upper(self) -> float:
        """Previous-bar channel high (excludes current bar)."""
        return self._prev_upper if self.is_ready else 0.0
        
    @property
    def lower(self) -> float:
        """Previous-bar channel low (excludes current bar)."""
        return self._prev_lower if self.is_ready else 0.0

class StandardDeviation(BaseIndicator):
    """Sample standard deviation of a rolling window."""
    
    @property
    def value(self) -> float:
        if not self.is_ready:
            return 0.0
        return float(np.std(self.values, ddof=1))
        
class VWAP:
    """Session or rolling Anchored Volume Weighted Average Price."""
    def __init__(self):
        self.cum_pv = 0.0
        self.cum_vol = 0.0
        
    def add(self, typical_price: float, volume: float):
        self.cum_pv += typical_price * volume
        self.cum_vol += volume
        
    def reset(self):
        self.cum_pv = 0.0
        self.cum_vol = 0.0
        
    @property
    def value(self) -> float:
        if self.cum_vol == 0:
            return 0.0
        return self.cum_pv / self.cum_vol
