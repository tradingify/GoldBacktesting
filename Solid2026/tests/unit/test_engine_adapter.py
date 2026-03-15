import unittest

import pandas as pd

from src.gold_research.backtests.engine.adapters import NautilusAdapter
from src.gold_research.backtests.specifications.experiment_spec import DatasetSpec, ExperimentSpec


class TestNautilusAdapter(unittest.TestCase):
    def test_infer_timeframe_from_manifest_id(self):
        spec = ExperimentSpec(
            experiment_id="exp_test",
            run_id="run_test",
            strategy_class_path="src.gold_research.strategies.trend.moving_average_cross.MovingAverageCross",
            strategy_params={"fast_period": 10, "slow_period": 20},
            dataset=DatasetSpec(
                manifest_id="gold_h1_2015_2024",
                instrument_id="XAUUSD-IDEALPRO-USD",
            ),
        )

        self.assertEqual(NautilusAdapter.infer_timeframe(spec), "1h")

    def test_slice_dataframe_to_window(self):
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    [
                        "2025-01-01T00:00:00Z",
                        "2025-01-02T00:00:00Z",
                        "2025-01-03T00:00:00Z",
                    ],
                    utc=True,
                ),
                "open": [1.0, 2.0, 3.0],
                "high": [1.1, 2.1, 3.1],
                "low": [0.9, 1.9, 2.9],
                "close": [1.0, 2.0, 3.0],
                "volume": [1, 1, 1],
            }
        )
        spec = ExperimentSpec(
            experiment_id="exp_test",
            run_id="run_test",
            strategy_class_path="src.gold_research.strategies.trend.moving_average_cross.MovingAverageCross",
            strategy_params={},
            dataset=DatasetSpec(
                manifest_id="gold_m5_2023",
                instrument_id="XAUUSD-IDEALPRO-USD",
                start_time="2025-01-02T00:00:00+00:00",
                end_time="2025-01-03T00:00:00+00:00",
            ),
        )

        filtered = NautilusAdapter.slice_dataframe_to_window(df, spec)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered["datetime"].iloc[0], pd.Timestamp("2025-01-02T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
