"""
Common Regime Filters.

Concrete implementations of `FilterBase` designed to block strategy
logic based on simple mechanics, like moving average alignment.
"""
from src.gold_research.strategies.base.filter_base import FilterBase
from src.gold_research.strategies.common.indicators import SimpleMovingAverage
from nautilus_trader.model.data import Bar

class MABaselineFilter(FilterBase):
    """
    Regime filter that requires price to be on a specific side
    of a massive moving average (e.g., 200 SMA).
    """
    def __init__(self, period: int = 200, direction: int = 1):
        """
        Args:
            period: Lookback of SMA.
            direction: 1 (requires close > MA), -1 (requires close < MA).
        """
        self.sma = SimpleMovingAverage(period)
        self.direction = direction
        
    def add_bar(self, bar: Bar):
         self.sma.add(float(bar.close))
         
    def is_active(self, bar: Bar) -> bool:
        if not self.sma.is_ready:
            return False
            
        current_price = float(bar.close)
        
        if self.direction == 1:
            return current_price > self.sma.value
        else:
            return current_price < self.sma.value