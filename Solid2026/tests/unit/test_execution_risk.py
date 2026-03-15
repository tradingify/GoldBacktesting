import unittest
import pandas as pd
from unittest.mock import patch

from src.gold_research.core.enums import ExecutionRegime, CostProfile
from src.gold_research.execution.cost_model import CostModelLoader, ExecutionCost
from src.gold_research.execution.slippage_model import SlippageModel
from src.gold_research.risk.position_sizing import PositionSizer
from src.gold_research.risk.exposure_limits import ExposureManager

class TestExecutionAndRisk(unittest.TestCase):
    
    @patch("src.gold_research.execution.cost_model.load_yaml")
    def test_cost_and_slippage_models(self, mock_load):
        # Mock global config yaml response
        mock_load.return_value = {
            "base": {"commission_per_order": 2.50, "spread": 0.10, "slippage": 0.05}
        }
        
        # Test Loader
        profile = CostModelLoader.get_profile(CostProfile.BASE)
        self.assertEqual(profile.slippage, 0.05)
        
        # Test Slippage Logic
        slippage = SlippageModel(profile)
        base_slip = slippage.estimate_slippage(10.0, ExecutionRegime.NORMAL)
        high_vol_slip = slippage.estimate_slippage(10.0, ExecutionRegime.HIGH_VOLATILITY)
        
        self.assertEqual(base_slip, 0.05)
        self.assertAlmostEqual(high_vol_slip, 0.15) # 3x penalty

    @patch("src.gold_research.risk.position_sizing.load_yaml")
    def test_fixed_fractional_sizing(self, mock_load):
        # Account size 100k, 1% risk = $1,000 risk capital
        sizer = PositionSizer(base_risk_pct=0.01)
        
        # Stop is $10 away. Contract multiplier = 100 per point ($1000 total risk per lot)
        # Expected size: 1 lot
        size = sizer.calculate_size_from_stop(
            account_equity=100000.0,
            entry_price=1900.0,
            stop_price=1890.0,
            contract_multiplier=100.0
        )
        self.assertEqual(size, 1.0)
        
        # Exception thrown on zero distance
        with self.assertRaises(ValueError):
             sizer.calculate_size_from_stop(100000, 1900, 1900)

    @patch("src.gold_research.risk.exposure_limits.load_yaml")
    def test_exposure_gatekeeper(self, mock_load):
        # Mock risk.yaml globally to 5% limits
        mock_load.return_value = {"max_exposure_per_strategy": 0.05}
        
        manager = ExposureManager()
        
        # Trying to put $5,000 to work on $100k account (Exactly 5%)
        # Open strategy allocation currently 0.
        allowed = manager.is_trade_allowed(5000.0, 100000.0, 0.0)
        self.assertTrue(allowed)
        
        # Trying to add $1,000 more (6% total exposure -> Denied)
        denied = manager.is_trade_allowed(1000.0, 100000.0, 5000.0)
        self.assertFalse(denied)

if __name__ == '__main__':
    unittest.main()
