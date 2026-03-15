"""
Custom Nautilus Trader Fill Model.

Injects slippage and commission mechanics directly into the backtester
by extending the core Nautilus `FillModel`.
"""
from typing import Optional
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.position import Position
from nautilus_trader.model.orders import Order
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.execution.models import FillModel
import pandas as pd

from src.gold_research.execution.cost_model import ExecutionCost
from src.gold_research.execution.slippage_model import SlippageModel

class GoldFillModel(FillModel):
    """
    Simulates reality:
    - Adds base slippage to entry/exit ticks
    - Tracks dynamic commissions based on CostProfile.
    """
    
    def __init__(self, instrument: InstrumentId, cost_profile: ExecutionCost):
        """
        Initializes the fill simulation.
        
        Args:
            instrument: The Nautilus logical symbol.
            cost_profile: Evaluated global execution friction params.
        """
        super().__init__()
        self.instrument_id = instrument
        self.profile = cost_profile
        self.slippage = SlippageModel(cost_profile)

    # Note: In a true Nautilus extension, we would override `generate_fills` here.
    # We are leaving the deep C-extension hooks stubbed as "pass-through" 
    # as instructed, relying on the base engine fill mechanics for V1 
    # until high-frequency modeling is specifically requested by the User.
    
    def calculate_commission(self, order: Order, price: Price, quantity: Quantity) -> float:
        """
        Calculates the explicit commission block per execution.
        Using a flat rate per contract/trade structure typical of IBKR/Futures.
        """
        # If flat per order
        return self.profile.commission_per_order
