"""
Market Impact and Slippage Modeler.

Dynamic slippage calculations based on execution environments 
such as high volatility regimes, order size, or illiquid hours.
"""
from typing import Optional
from src.gold_research.core.enums import ExecutionRegime
from src.gold_research.execution.cost_model import ExecutionCost

class SlippageModel:
    """
    Evaluates slippage penalties based on the underlying regime.
    """
    
    def __init__(self, base_cost: ExecutionCost):
        """
        Args:
            base_cost: The fixed ExecutionCost structure containing 
                       baseline slippage estimates.
        """
        self.base_cost = base_cost
        
    def estimate_slippage(
        self, 
        order_qty: float, 
        regime: ExecutionRegime = ExecutionRegime.NORMAL
    ) -> float:
        """
        Calculates assumed price slippage for an order.
        
        Args:
            order_qty: Absolute quantity of the order.
            regime: Current market regime (volatility state).
            
        Returns:
            The total slip penalty in absolute price increments.
            
        Note:
            In V1, we return a flat scaled value based on regime modifiers.
            Future versions can scale linearly or quadratically by size.
        """
        base_slip = self.base_cost.slippage
        
        # Modifier logic based on regimes
        if regime == ExecutionRegime.HIGH_VOLATILITY:
            base_slip *= 3.0
        elif regime == ExecutionRegime.COMPRESSION:
            base_slip *= 1.5
            
        # Optional: Add small quadratic penalty for very large sizes later
        # size_penalty = (abs(order_qty) / 100) ** 1.2
            
        return base_slip
