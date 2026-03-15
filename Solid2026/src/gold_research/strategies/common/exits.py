"""
Common Exit Trajectories.

Concrete exit strategies such as Trailing Stops or Timed Exits
implementing the `ExitBase` protocol.
"""
from typing import Optional
from nautilus_trader.model.data import Bar
from nautilus_trader.model.position import Position
from src.gold_research.strategies.base.exit_base import ExitBase

class FixedHoldTimeExit(ExitBase):
    """
    Exits a position indiscriminately after N bars have passed
    since the position was opened.
    """
    
    def __init__(self, bar_limit: int):
        self.bar_limit = bar_limit
        self.bars_held = 0
        
    def should_exit(self, bar: Bar, position: Optional[Position] = None) -> bool:
        if position is None:
            return False
            
        # In a real engine, we'd query the exact trade open time. 
        # Here we increment a stateful ticker.
        self.bars_held += 1
        
        if self.bars_held >= self.bar_limit:
            self.bars_held = 0
            return True
            
        return False
        
class TrailATRStopExit(ExitBase):
    """
    Exits dynamically if price crosses an ATR-based trail threshold.
    """
    
    def __init__(self, atr_multiplier: float):
        self.atr_multiplier = atr_multiplier
        self.trail_level = None
        
    def update_trail(self, current_price: float, atr: float, direction: int):
        """Called by strategy loop to push trail forward."""
        if direction == 1: # Long
            new_level = current_price - (atr * self.atr_multiplier)
            if self.trail_level is None or new_level > self.trail_level:
                 self.trail_level = new_level
        else: # Short
            new_level = current_price + (atr * self.atr_multiplier)
            if self.trail_level is None or new_level < self.trail_level:
                 self.trail_level = new_level
                 
    def should_exit(self, bar: Bar, position: Optional[Position] = None) -> bool:
        if self.trail_level is None or position is None:
            return False
            
        close = float(bar.close)
        
        if position.is_long and close <= self.trail_level:
            return True
        elif position.is_short and close >= self.trail_level:
            return True
            
        return False