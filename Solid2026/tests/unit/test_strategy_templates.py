import unittest

class TestStrategyTemplates(unittest.TestCase):
    
    def test_import_trend_strategies(self):
        from src.gold_research.strategies.trend.donchian_breakout import DonchianBreakout
        from src.gold_research.strategies.trend.moving_average_cross import MovingAverageCross
        from src.gold_research.strategies.trend.atr_breakout import ATRBreakout
        self.assertTrue(True)
        
    def test_import_reversion_strategies(self):
        from src.gold_research.strategies.mean_reversion.bollinger_reversion import BollingerReversion
        from src.gold_research.strategies.mean_reversion.zscore_reversion import ZScoreReversion
        from src.gold_research.strategies.mean_reversion.vwap_reversion import VWAPReversion
        self.assertTrue(True)
        
    def test_import_breakout_strategies(self):
        from src.gold_research.strategies.breakout.opening_range_breakout import OpeningRangeBreakout
        from src.gold_research.strategies.breakout.squeeze_breakout import SqueezeBreakout
        self.assertTrue(True)
        
    def test_import_pullback_strategies(self):
        from src.gold_research.strategies.pullback.ema_pullback import EMAPullback
        self.assertTrue(True)
        
    def test_import_hybrid_strategies(self):
        from src.gold_research.strategies.hybrid.regime_switching_breakout_reversion import RegimeSwitchingBreakoutReversion
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
