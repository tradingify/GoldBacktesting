"""
Exit Logic Protocol.

Defines the interface for modules that manage open positions, 
such as trailing stops, time-exits, or profit targets.
"""
from abc import ABC, abstractmethod
from typing import Optional
from nautilus_trader.model.data import Bar
from nautilus_trader.model.position import Position

class ExitBase(ABC):
    """
    Abstract blueprint for an exit manager.
    Constantly polls the market to determine if a position should be liquidated.
    """
    
    @abstractmethod
    def should_exit(self, current_bar: Bar, position: Optional[Position] = None) -> bool:
        """
        Evaluates the open parameters.
        
        Args:
            current_bar: The latest market update.
            position: Optional specific position reference (if logic depends on entry price).
            
        Returns:
            True if liquidation signal generated, else False.
        """
        pass