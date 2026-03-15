"""
Base Strategy Architecture.

Provides the foundational `GoldStrategy` class extending Nautilus Trader.
Enforces a highly modular, composable structure where Strategies are built
by snapping together pure Logic components (Entry, Exit, Filter, Sizing).
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Any
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.trading.strategy import Strategy

# Maps shorthand timeframe strings -> (step size, BarAggregation enum)
_TIMEFRAME_MAP = {
    "1m":   (1, BarAggregation.MINUTE),
    "5m":   (5, BarAggregation.MINUTE),
    "15m":  (15, BarAggregation.MINUTE),
    "30m":  (30, BarAggregation.MINUTE),
    "1h":   (1, BarAggregation.HOUR),
    "4h":   (4, BarAggregation.HOUR),
    "1d":   (1, BarAggregation.DAY),
}

class GoldStrategyConfig(StrategyConfig):
    """Base configuration type required by all Gold Factory strategies."""
    instrument_id: str
    timeframe: str
    
class GoldStrategy(Strategy, ABC):
    """
    Core framework strategy. 
    Enforces the composition pattern mandated by the Master Plan.
    Subclasses must wire together their Logic blocks in `on_start`.
    """
    
    def __init__(self, config: GoldStrategyConfig):
        super().__init__(config)
        self.instrument_id_str = config.instrument_id
        self.timeframe = config.timeframe
        self._nautilus_instrument_id = None
        
        # Composable Logic Blocks (To be defined by subclasses)
        self.regime_filter = None
        self.signal_generator = None
        self.entry_logic = None
        self.exit_logic = None
        self.position_sizer = None
    
    @property
    def nautilus_instrument_id(self) -> InstrumentId:
        """Lazily build and cache the Nautilus InstrumentId from the string config."""
        if self._nautilus_instrument_id is None:
            parts = self.instrument_id_str.split("-") if isinstance(self.instrument_id_str, str) else [str(self.instrument_id_str)]
            symbol_str = parts[0]
            venue_str = parts[1] if len(parts) > 1 else "SIM"
            self._nautilus_instrument_id = InstrumentId(Symbol(symbol_str), Venue(venue_str))
        return self._nautilus_instrument_id
    
    # ----- Portfolio convenience helpers (wraps Nautilus API) -----
    
    @property
    def is_invested(self) -> bool:
        """True if we have any open position on this instrument."""
        return not self.portfolio.is_flat(self.nautilus_instrument_id)
    
    @property
    def is_long(self) -> bool:
        """True if we are net long on this instrument."""
        return self.portfolio.is_net_long(self.nautilus_instrument_id)
    
    @property
    def is_short(self) -> bool:
        """True if we are net short on this instrument."""
        return self.portfolio.is_net_short(self.nautilus_instrument_id)
        
    def _build_bar_type(self) -> BarType:
        """Build the BarType matching the data feed for this strategy's instrument and timeframe."""
        step, aggregation = _TIMEFRAME_MAP[self.timeframe]
        bar_spec = BarSpecification(step, aggregation, PriceType.LAST)
        return BarType(self.nautilus_instrument_id, bar_spec, AggregationSource.EXTERNAL)
        
    def on_start(self):
        """Called by Nautilus when the engine boots. Subscribes to bars and inits components."""
        self.setup_components()
        
        # Subscribe to the bar feed matching this strategy's timeframe
        if self.timeframe in _TIMEFRAME_MAP:
            bar_type = self._build_bar_type()
            self.subscribe_bars(bar_type)
        
    @abstractmethod
    def setup_components(self):
        """
        Required hook for subclasses.
        Instantiate and assign `self.signal_generator`, `self.entry_logic`, etc.
        """
        pass
        
    def on_bar(self, bar: Bar):
        """
        Main event loop executed by Nautilus.
        Executes the logical pipeline sequentially.
        """
        # 1. Update Indicators & Logic State
        self.update_state(bar)
        
        # 2. Check Exits (Manage existing positions)
        if self.is_invested:
            self.evaluate_exits(bar)
            
        # 3. Check Entries (If flat, evaluate new opportunities)
        if not self.is_invested:
            self.evaluate_entries(bar)
            
    @abstractmethod
    def update_state(self, bar: Bar):
        """Update any custom indicators or state machines specific to this strategy."""
        pass
        
    def evaluate_exits(self, bar: Bar):
        """Polls the `exit_logic` module. Triggers liquidations if required."""
        if not self.exit_logic:
            return
        # Get the active positions for this instrument
        positions = self.cache.positions(instrument_id=self.nautilus_instrument_id)
        open_positions = [p for p in positions if p.is_open]
        for position in open_positions:
            if self.exit_logic.should_exit(bar, position):
                self.close_position(position)
            
    def evaluate_entries(self, bar: Bar):
        """
        Executes the sequence: Regime -> Signal -> Sizing -> Entry Execution.
        """
        # A. Regime Filter Gatekeeper
        if self.regime_filter and not self.regime_filter.is_active(bar):
            return
            
        # B. Signal Generation
        if self.signal_generator:
            signal = self.signal_generator.generate(bar)
            if not signal:
                return
                
            # C. Determine Size
            qty = 1.0 # default fallback
            if self.position_sizer:
                qty = self.position_sizer.calculate_size(signal, bar, self)
                
            # D. Execute Entry Mechanics
            if self.entry_logic:
                self.entry_logic.execute(signal, qty, bar, self)
