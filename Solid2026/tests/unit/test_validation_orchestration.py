import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.gold_research.backtests.orchestration.run_stress_suite import run_stress_suite
from src.gold_research.backtests.orchestration.run_walkforward import generate_wfo_windows, run_walkforward
from src.gold_research.backtests.specifications.experiment_spec import DatasetSpec, ExperimentSpec
from src.gold_research.backtests.specifications.parameter_grid import ParameterGrid


class _FakePipelineResult:
    def __init__(self, run_id: str, sharpe: float):
        self.run_id = run_id
        self.experiment_id = "exp"
        self.status = "COMPLETED"
        self.run_dir = Path("D:/tmp") / run_id
        self.error_text = None
        self.artifacts = {}
        self.scorecard = type(
            "Scorecard",
            (),
            {
                "model_dump": lambda self_: {
                    "run_id": run_id,
                    "total_trades": 200,
                    "win_rate": 0.55,
                    "profit_factor": 1.5,
                    "total_net_profit": 5000.0,
                    "sharpe": sharpe,
                    "sortino": 2.0,
                    "calmar": 1.0,
                    "max_dd_pct": -0.10,
                    "status": "COMPLETED",
                },
                "sharpe": sharpe,
            },
        )()


class TestValidationOrchestration(unittest.TestCase):
    def _base_spec(self) -> ExperimentSpec:
        return ExperimentSpec(
            experiment_id="exp_validation",
            run_id="parent_run",
            strategy_class_path="src.gold_research.strategies.trend.moving_average_cross.MovingAverageCross",
            strategy_params={"fast_period": 10, "slow_period": 20},
            dataset=DatasetSpec(
                manifest_id="gold_m5_2023",
                instrument_id="XAUUSD-IDEALPRO-USD",
                start_time="2025-01-01T00:00:00+00:00",
                end_time="2025-12-31T00:00:00+00:00",
            ),
        )

    def test_generate_wfo_windows(self):
        from datetime import datetime, UTC

        windows = generate_wfo_windows(
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 12, 31, tzinfo=UTC),
            is_days=120,
            oos_days=30,
        )
        self.assertGreater(len(windows), 0)

    def test_run_stress_suite_aggregates_profiles(self):
        import src.gold_research.backtests.orchestration.run_stress_suite as stress_module

        original = stress_module.run_single_pipeline_with_context

        def fake_run_single_pipeline_with_context(spec, **kwargs):
            sharpe_by_profile = {"optimistic": 2.0, "base": 1.5, "harsh": 0.75}
            return _FakePipelineResult(spec.run_id, sharpe_by_profile[spec.costs.profile_name])

        stress_module.run_single_pipeline_with_context = fake_run_single_pipeline_with_context
        try:
            result = run_stress_suite(self._base_spec())
        finally:
            stress_module.run_single_pipeline_with_context = original

        self.assertEqual(len(result["suite_results"]), 3)
        self.assertIn("stress_decay", result["summary"])

    def test_run_walkforward_executes_is_and_oos(self):
        import src.gold_research.backtests.orchestration.run_walkforward as wfo_module

        original = wfo_module.run_single_pipeline_with_context

        def fake_run_single_pipeline_with_context(spec, **kwargs):
            sharpe = 2.0 if kwargs.get("run_type") == "walkforward_is" else 1.0
            return _FakePipelineResult(spec.run_id, sharpe)

        wfo_module.run_single_pipeline_with_context = fake_run_single_pipeline_with_context
        try:
            result = run_walkforward(
                self._base_spec(),
                ParameterGrid({"fast_period": [10, 20], "slow_period": [30]}),
                is_days=120,
                oos_days=30,
            )
        finally:
            wfo_module.run_single_pipeline_with_context = original

        self.assertGreater(len(result["is_grid_results"]), 0)
        self.assertGreater(len(result["oos_live_track"]), 0)
        self.assertIn("wfo_efficiency", result["summary"])


if __name__ == "__main__":
    unittest.main()
