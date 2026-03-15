import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from src.gold_research.store.db import initialize_database
from src.gold_research.store.runs_repo import RunsRepository


class TestResearchStore(unittest.TestCase):
    def test_initialize_database_creates_core_tables(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "research.db"
            initialize_database(db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }

            self.assertIn("runs", tables)
            self.assertIn("run_artifacts", tables)

    def test_runs_repository_persists_run_and_artifacts(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "research.db"
            repo = RunsRepository(db_path)
            repo.upsert_run(
                run_id="run_test_001",
                experiment_id="exp_test",
                status="completed",
                strategy_class_path="pkg.Strategy",
                dataset_manifest_id="dataset_v1",
                timeframe="5m",
                started_at="2026-03-14T00:00:00+00:00",
                completed_at="2026-03-14T00:01:00+00:00",
            )
            repo.record_artifacts(
                "run_test_001",
                [("scorecard", "D:/tmp/scorecard.json"), ("metrics", "D:/tmp/metrics.json")],
            )

            with closing(sqlite3.connect(db_path)) as conn:
                run_row = conn.execute(
                    "SELECT run_id, status, dataset_manifest_id FROM runs WHERE run_id = ?",
                    ("run_test_001",),
                ).fetchone()
                artifact_count = conn.execute(
                    "SELECT COUNT(*) FROM run_artifacts WHERE run_id = ?",
                    ("run_test_001",),
                ).fetchone()[0]

            self.assertEqual(run_row[0], "run_test_001")
            self.assertEqual(run_row[1], "completed")
            self.assertEqual(run_row[2], "dataset_v1")
            self.assertEqual(artifact_count, 2)


if __name__ == "__main__":
    unittest.main()
