import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from src.gold_research.backtests.specifications.experiment_spec import DatasetSpec, ExperimentSpec
from src.gold_research.core.ids import generate_run_fingerprint
from src.gold_research.orchestration.batch_runner import enqueue_specs
from src.gold_research.store.queue_repo import QueueRepository


class TestBatchRunner(unittest.TestCase):
    def test_run_fingerprint_is_stable(self):
        fp1 = generate_run_fingerprint(
            experiment_id="exp1",
            strategy_class_path="pkg.Strategy",
            strategy_params={"a": 1, "b": 2},
            dataset_manifest_id="dataset1",
            instrument_id="XAUUSD-IDEALPRO-USD",
            start_time=None,
            end_time=None,
            cost_profile="base",
            risk_profile="base",
        )
        fp2 = generate_run_fingerprint(
            experiment_id="exp1",
            strategy_class_path="pkg.Strategy",
            strategy_params={"b": 2, "a": 1},
            dataset_manifest_id="dataset1",
            instrument_id="XAUUSD-IDEALPRO-USD",
            start_time=None,
            end_time=None,
            cost_profile="base",
            risk_profile="base",
        )
        self.assertEqual(fp1, fp2)

    def test_queue_deduplicates_identical_specs(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "research.db"
            base_spec = ExperimentSpec(
                experiment_id="exp_batch",
                run_id="parent_run",
                strategy_class_path="src.gold_research.strategies.trend.moving_average_cross.MovingAverageCross",
                strategy_params={},
                dataset=DatasetSpec(
                    manifest_id="gold_m5_2023",
                    instrument_id="XAUUSD-IDEALPRO-USD",
                ),
            )
            combos = [{"fast_period": 10, "slow_period": 20}, {"fast_period": 10, "slow_period": 20}]

            # Create the queue directly against an isolated temp DB.
            queue_repo = QueueRepository(db_path)
            self.assertIsNotNone(queue_repo)

            # Import here so we can patch the queue repo db path through the environment-free approach below.
            from src.gold_research.orchestration import batch_runner

            original_repo = batch_runner.QueueRepository

            class TempQueueRepository(QueueRepository):
                def __init__(self):
                    super().__init__(db_path)

            batch_runner.QueueRepository = TempQueueRepository
            try:
                summary = enqueue_specs(base_spec, combos, run_type="grid")
            finally:
                batch_runner.QueueRepository = original_repo

            self.assertEqual(summary["submitted"], 1)
            self.assertEqual(summary["skipped"], 1)

            with closing(sqlite3.connect(db_path)) as conn:
                count = conn.execute("SELECT COUNT(*) FROM run_queue").fetchone()[0]
            self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
