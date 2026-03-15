"""
VWAP Reversion Strategy.

Hypothesis: Institutional volume clusters around the daily Volume Weighted
Average Price. Intraday price extensions significantly away from the VWAP 
without breaking volume paradigms will violently snap back to the VWAP anchor.

Note: Requires 1-minute or 5-minute Intraday datasets. Spot Gold volume is 
often 0 tracked, so we fallback to assuming linear volume per tick for pure 
time-weighted behavior if needed.
"""
from typing import Optional
from nautilus_trader.model.data import Bar

from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import VWAP
from src.gold_research.strategies.common.sizing import DynamicRiskSizer
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.exits import FixedHoldTimeExit

class VWAPReversionSignal(SignalBase):
    def __init__(self, return_threshold_pct: float = 0.005):
        self.vwap = VWAP()
        self.return_threshold_pct = return_threshold_pct
        self.current_day = None
        
    def update(self, bar: Bar):
         # Session resetting logic based on naive UTC date crossovers
         # More complex session resets can be introduced later via sessions.yaml
         dt = pd.to_datetime(bar.ts_event, unit="ns", utc=True)
         date_str = dt.strftime("%Y-%m-%d")
         
         if self.current_day is None or self.current_day != date_str:
             self.current_day = date_str
             self.vwap.reset()
             
         high, low, close = float(bar.high), float(bar.low), float(bar.close)
         typical_price = (high + low + close) / 3.0
         
         # Fallback on 1 volume if Gold feeds stream 0 to maintain TWAP parity
         vol = float(bar.volume)
         if vol == 0:
             vol = 1.0
             
         self.vwap.add(typical_price, vol)
         
    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        vw_val = self.vwap.value
        if vw_val == 0.0:
            return None
            
        close = float(bar.close)
        dist_pct = (close / vw_val) - 1.0
        
        # Simple stop placed far enough beyond to act as invalidation
        # Real stops should be tied to structural pivots
        stop_offset = close * 0.01 
        
        if dist_pct > self.return_threshold_pct:
            # Price is significantly above VWAP -> Short back
            return SignalIntent(-1, close, close + stop_offset)
        elif dist_pct < -self.return_threshold_pct:
            # Price is significantly below VWAP -> Long back
            return SignalIntent(1, close, close - stop_offset)
            
        return None

class VWAPReversionConfig(GoldStrategyConfig):
    return_threshold_pct: float = 0.005 # 0.5% away triggers revert setup
    hold_bars: int = 12 # ~1hr on 5m chart

class VWAPReversion(GoldStrategy):
    
    def __init__(self, config: VWAPReversionConfig):
        super().__init__(config)
        self.cfg = config
        
    def setup_components(self):
        self.signal_generator = VWAPReversionSignal(self.cfg.return_threshold_pct)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = FixedHoldTimeExit(self.cfg.hold_bars)
        self.position_sizer = DynamicRiskSizer()
        
    def update_state(self, bar: Bar):
        self.signal_generator.update(bar)