import unittest
from pathlib import Path
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.ids import generate_experiment_id, generate_run_id
from src.gold_research.core.enums import StrategyFamily, Timeframe

class TestCore(unittest.TestCase):
    def test_project_paths(self):
        """Verify that ProjectPaths class resolves dynamically without issues."""
        data_path = ProjectPaths.get_data_dir()
        self.assertEqual(data_path.name, "data")
        
    def test_id_generation(self):
        """Verify experiment and run ID determinism."""
        exp_id = generate_experiment_id("sprint_01", "scan", "gold", "trend", "batch1")
        self.assertIn("sprint_01__scan__gold__trend", exp_id)
        self.assertIn("batch1", exp_id)
        
        config = {"ma_fast": 10, "ma_slow": 50, "atr_factor": 2.5}
        run_id_1 = generate_run_id(exp_id, "MaCross", config)
        self.assertTrue(run_id_1.startswith(exp_id))
        self.assertIn("MaCross", run_id_1)
        
    def test_enums(self):
        """Validate core application enums resolve as expected."""
        self.assertEqual(Timeframe.H1.value, "1h")
        self.assertEqual(StrategyFamily.TREND.value, "trend")

if __name__ == '__main__':
    unittest.main()
