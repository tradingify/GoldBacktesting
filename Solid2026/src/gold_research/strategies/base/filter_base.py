"""
Filter Base Protocol.

Regime filters act as boolean gatekeepers that prevent
Signal Generators from evaluating setups when the market environment
is structurally unfavorable.
"""
from abc import ABC, abstractmethod
from nautilus_trader.model.data import Bar

class FilterBase(ABC):
    """Abstract blueprint for a market regime filter."""
    
    @abstractmethod
    def is_active(self, current_bar: Bar) -> bool:
        """
        Evaluates filter logic.
        
        Returns:
            True if the market regime is acceptable for trading, False otherwise.
        """
        pass