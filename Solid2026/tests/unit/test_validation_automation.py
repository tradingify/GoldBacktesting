import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.gold_research.backtests.specifications.experiment_spec import DatasetSpec, ExperimentSpec
from src.gold_research.validation.automation import (
    build_validation_grid,
    run_automatic_validation,
    should_auto_validate,
)


class TestValidationAutomation(unittest.TestCase):
    def _spec(self) -> ExperimentSpec:
        return ExperimentSpec(
            experiment_id="exp_auto_validation",
            run_id="winner_run",
            strategy_class_path="src.gold_research.strategies.mean_reversion.bollinger_reversion.BollingerReversion",
            strategy_params={"timeframe": "15m", "period": 20, "std_devs": 2.0, "hold_bars": 5},
            dataset=DatasetSpec(
                manifest_id="xauusd_15_mins",
                instrument_id="XAUUSD-IDEALPRO-USD",
                start_time="2025-08-01T00:00:00+00:00",
                end_time="2025-08-31T23:59:59+00:00",
            ),
        )

    def test_should_auto_validate_only_for_eligible_completed_single_runs(self):
        self.assertTrue(should_auto_validate("single", "soft_fail", "COMPLETED"))
        self.assertFalse(should_auto_validate("grid", "soft_fail", "COMPLETED"))
        self.assertFalse(should_auto_validate("single", "hard_fail", "COMPLETED"))
        self.assertFalse(should_auto_validate("single", "pass", "FAILED"))

    def test_build_validation_grid_creates_numeric_neighbors(self):
        grid = list(build_validation_grid(self._spec().strategy_params).generate_grid())
        self.assertGreater(len(grid), 1)
        periods = sorted({item["period"] for item in grid})
        self.assertIn(20, periods)
        self.assertIn(16, periods)
        self.assertIn(24, periods)

    def test_run_automatic_validation_can_skip_ineligible_runs(self):
        with TemporaryDirectory() as tmpdir:
            payload = run_automatic_validation(
                self._spec(),
                run_dir=Path(tmpdir),
                screening_status="hard_fail",
                run_type="single",
            )
        self.assertEqual(payload["automation_status"], "skipped")

    def test_run_automatic_validation_persists_combined_decision(self):
        import src.gold_research.validation.automation as automation_module

        original_wfo = automation_module.__dict__.get("run_walkforward")
        original_stress = automation_module.__dict__.get("run_stress_suite")
        original_repo = automation_module.PromotionsRepository
        try:
            def fake_run_walkforward(spec, grid, is_days, oos_days):
                return {"summary": {"wfo_efficiency": 0.8, "folds": 2}}

            def fake_run_stress_suite(spec):
                return {"summary": {"stress_decay": 0.8}}

            class FakePromotionsRepository:
                def upsert_gate_result(self, **kwargs):
                    return None

                def upsert_promotion(self, **kwargs):
                    return None

            # Prime module globals so the helper uses the fakes.
            automation_module.run_walkforward = fake_run_walkforward
            automation_module.run_stress_suite = fake_run_stress_suite
            automation_module.PromotionsRepository = FakePromotionsRepository

            with TemporaryDirectory() as tmpdir:
                payload = run_automatic_validation(
                    self._spec(),
                    run_dir=Path(tmpdir),
                    screening_status="soft_fail",
                    run_type="single",
                )
                self.assertEqual(payload["automation_status"], "completed")
                self.assertEqual(payload["decision"]["promotion_state"], "candidate_for_portfolio")
                self.assertTrue((Path(tmpdir) / "validation_summary.json").exists())
        finally:
            if original_wfo is None:
                automation_module.__dict__.pop("run_walkforward", None)
            else:
                automation_module.run_walkforward = original_wfo
            if original_stress is None:
                automation_module.__dict__.pop("run_stress_suite", None)
            else:
                automation_module.run_stress_suite = original_stress
            automation_module.PromotionsRepository = original_repo


if __name__ == "__main__":
    unittest.main()
