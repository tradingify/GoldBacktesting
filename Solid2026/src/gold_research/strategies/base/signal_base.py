"""
Signal Generator Protocol.

Defines the interface for modules determining directional trade intentions.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from nautilus_trader.model.data import Bar

class SignalIntent:
    """Standardized message passed from Signal Generator to Sizing/Execution."""
    def __init__(self, direction: int, entry_price: float, stop_price: float, metadata: Dict[str, Any] = None):
        self.direction = direction  # 1 for Long, -1 for Short
        self.entry_price = entry_price
        self.stop_price = stop_price
        self.metadata = metadata or {}

class SignalBase(ABC):
    """
    Abstract blueprint for a signal generator.
    Evaluates market state and emits intentions if conditions are met.
    """
    
    @abstractmethod
    def generate(self, current_bar: Bar) -> Optional[SignalIntent]:
        """
        Returns a SignalIntent if a setup is valid, else None.
        """
        pass