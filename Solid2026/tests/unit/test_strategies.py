import unittest
from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.common.indicators import SimpleMovingAverage, TrueRange
from src.gold_research.strategies.common.helpers import crossover, crossunder

class MockSignal(SignalBase):
    def generate(self, bar):
        return SignalIntent(1, float(bar.close), float(bar.close) - 10)
        
class TestStrategies(unittest.TestCase):
    def test_indicators(self):
        sma = SimpleMovingAverage(3)
        self.assertFalse(sma.is_ready)
        sma.add(10)
        sma.add(20)
        sma.add(30)
        self.assertTrue(sma.is_ready)
        self.assertEqual(sma.value, 20.0)
        
    def test_helpers_crossover(self):
        fast = [10, 15, 25]
        slow = [10, 20, 20]
        # fast crossed above slow on latest tick
        self.assertTrue(crossover(fast, slow))
        self.assertFalse(crossunder(fast, slow))
        
    def test_signal_intent(self):
        s = MockSignal()
        # mock bar not needed for this stub test since it's just syntax validation
        intent = SignalIntent(direction=-1, entry_price=1900, stop_price=1910)
        self.assertEqual(intent.direction, -1)

if __name__ == '__main__':
    unittest.main()
