"""
Common Entry Execution Logistics.

Modules responsible for taking a concrete `SignalIntent` and
firing the correct orders into the Nautilus trading venue.
"""
from typing import Optional
from nautilus_trader.model.data import Bar
from nautilus_trader.model.instruments import Instrument
from src.gold_research.strategies.base.signal_base import SignalIntent

class MarketEntryExecutor:
    """Executes signals strictly at the market."""
    
    def __init__(self, venue: str = "SIM"):
        self.venue = venue
        
    def execute(self, signal: SignalIntent, size: float, bar: Bar, strategy_ref) -> None:
        """
        Sends the Market order via the parent Nautilus strategy.
        
        Args:
            signal: The directional intent wrapper.
            size: Fractional position limit computed by Sizing modules.
            bar: The current event trigger.
            strategy_ref: Pointer to Nautilus `Strategy` invoking the order.
        """
        instrument_id = strategy_ref.nautilus_instrument_id
        inst: Instrument = strategy_ref.cache.instrument(instrument_id)
        
        # Ensure at least 1 unit before rounding
        raw_size = max(abs(size), 1.0)
        qty = inst.make_qty(raw_size)
        
        # Safety: skip if qty is still 0 after rounding
        if float(qty) <= 0:
            return
        
        if signal.direction == 1:
            order = strategy_ref.order_factory.market(
                instrument_id=instrument_id,
                order_side=int(1), # nautilus OrderSide.BUY equivalent
                quantity=qty
            )
        else:
            order = strategy_ref.order_factory.market(
                instrument_id=instrument_id,
                order_side=int(2), # nautilus OrderSide.SELL equivalent
                quantity=qty
            )
            
        strategy_ref.submit_order(order)