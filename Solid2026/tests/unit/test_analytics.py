import unittest
import pandas as pd
import numpy as np

class TestAnalytics(unittest.TestCase):
    def test_imports_and_basic_math(self):
        from src.gold_research.analytics.metrics import sharpe_ratio
        from src.gold_research.analytics.scorecards import generate_scorecard
        from src.gold_research.analytics.robustness import RobustnessAnalyzer
        from src.gold_research.analytics.sensitivity import SensitivityAnalysis
        from src.gold_research.analytics.regimes import RegimeAnalyzer
        from src.gold_research.analytics.equity import EquityAnalyzer
        from src.gold_research.analytics.trade_analysis import TradeAnalyzer
        from src.gold_research.analytics.clustering import ClusteringAnalyzer
        from src.gold_research.analytics.portfolio import PortfolioComposer
        
        # Test basic metric (Sharpe)
        returns = pd.Series([0.01, 0.02, -0.01, 0.03, -0.02])
        sharpe = sharpe_ratio(returns)
        self.assertIsInstance(sharpe, float)
        self.assertNotEqual(sharpe, float('nan'))

if __name__ == '__main__':
    unittest.main()
