import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.gold_research.backtests.specifications.experiment_spec import DatasetSpec, ExperimentSpec
from src.gold_research.pipeline.run_pipeline import run_single_pipeline_with_context


class _FakeTrader:
    def generate_positions_report(self):
        return pd.DataFrame({"realized_pnl": ["100 USD", "-40 USD", "60 USD"]})

    def generate_order_fills_report(self):
        return pd.DataFrame({"price": [1900.0, 1902.0], "qty": [1, 1]})

    def portfolios(self):
        return {}


class _FakeEngine:
    def __init__(self):
        self.trader = _FakeTrader()


class TestPipelineSmoke(unittest.TestCase):
    def test_canonical_run_pipeline_writes_artifacts_and_db_state(self):
        import src.gold_research.store.db as store_db
        import src.gold_research.core.paths as core_paths
        import src.gold_research.core.artifacts as artifacts_module
        import src.gold_research.backtests.engine.nautilus_runner as runner_module

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_dir = root / "results"
            data_dir = root / "data"
            results_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)

            original_db_path = store_db.DB_PATH
            original_results = core_paths.ProjectPaths.RESULTS
            original_data = core_paths.ProjectPaths.DATA
            original_runner = runner_module.NautilusRunner.run

            def fake_run(self):
                return {
                    "run_id": self.spec.run_id,
                    "status": "COMPLETED",
                    "engine": _FakeEngine(),
                    "positions_report": _FakeTrader().generate_positions_report(),
                    "fills_report": _FakeTrader().generate_order_fills_report(),
                }

            store_db.DB_PATH = data_dir / "manifests" / "research.db"
            core_paths.ProjectPaths.RESULTS = results_dir
            core_paths.ProjectPaths.DATA = data_dir
            artifacts_module.ProjectPaths.RESULTS = results_dir
            runner_module.NautilusRunner.run = fake_run
            try:
                spec = ExperimentSpec(
                    experiment_id="EXP_SMOKE",
                    run_id="run_smoke_001",
                    strategy_class_path="src.gold_research.strategies.trend.moving_average_cross.MovingAverageCross",
                    strategy_params={"fast_period": 10, "slow_period": 20, "timeframe": "5m"},
                    dataset=DatasetSpec(
                        manifest_id="gold_m5_2023",
                        instrument_id="XAUUSD-IDEALPRO-USD",
                    ),
                )
                result = run_single_pipeline_with_context(spec, run_type="single")
            finally:
                store_db.DB_PATH = original_db_path
                core_paths.ProjectPaths.RESULTS = original_results
                core_paths.ProjectPaths.DATA = original_data
                artifacts_module.ProjectPaths.RESULTS = original_results
                runner_module.NautilusRunner.run = original_runner

            run_dir = results_dir / "raw_runs" / "EXP_SMOKE" / "run_smoke_001"
            self.assertEqual(result.status, "COMPLETED")
            self.assertTrue((run_dir / "scorecard.json").exists())
            self.assertTrue((run_dir / "gate_results.json").exists())

            with open(run_dir / "gate_results.json", "r", encoding="utf-8") as handle:
                gate_payload = json.load(handle)
            self.assertIn(gate_payload["promotion_state"], {"candidate_for_robustness", "hold_for_review", "rejected"})

            with closing(sqlite3.connect(data_dir / "manifests" / "research.db")) as conn:
                run_row = conn.execute("SELECT status FROM runs WHERE run_id = 'run_smoke_001'").fetchone()
                promotion_row = conn.execute("SELECT promotion_state FROM promotions WHERE run_id = 'run_smoke_001'").fetchone()
            self.assertIsNotNone(run_row)
            self.assertIsNotNone(promotion_row)


if __name__ == "__main__":
    unittest.main()
