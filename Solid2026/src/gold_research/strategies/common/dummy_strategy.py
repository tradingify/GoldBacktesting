from ...core.enums import StrategyFamily
from ..base.strategy_base import BaseStrategy, BaseStrategyConfig
from ...risk.position_sizing import PositionSizer
from nautilus_trader.model.data import Bar
from nautilus_trader.trading.strategy import StrategyConfig
from pydantic import Field

class DummyStrategyConfig(BaseStrategyConfig):
    family: StrategyFamily = StrategyFamily.TREND
    
class DummyStrategy(BaseStrategy):
    config: DummyStrategyConfig
    
    def __init__(self, config: DummyStrategyConfig):
        super().__init__(config)
        self.sizer = PositionSizer(self.base_risk_per_trade)
        
    def on_bar(self, bar: Bar):
        # Extremely simplistic: Just prints that a bar arrived so we know Nautilus works.
        # In later stages this will hold logic calling `self.submit_order()`
        pass
