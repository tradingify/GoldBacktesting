import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

import pandas as pd

from src.gold_research.core.artifacts import build_run_manifest, write_dataframe_csv, write_json


class TestArtifacts(unittest.TestCase):
    def test_write_json_and_dataframe_csv(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            json_path = write_json(root / "metrics.json", {"status": "ok"})
            csv_path = write_dataframe_csv(root / "fills.csv", pd.DataFrame({"price": [1.0, 2.0]}))

            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())

            with open(json_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

            self.assertEqual(payload["status"], "ok")

    def test_build_run_manifest(self):
        manifest = build_run_manifest(
            run_id="run_123",
            experiment_id="exp_abc",
            dataset_manifest_id="gold_primary",
            strategy_class_path="pkg.Strategy",
            strategy_params={"lookback": 20},
            timeframe="15m",
            status="COMPLETED",
            artifact_paths={"scorecard": "D:/scorecard.json"},
        )

        self.assertEqual(manifest["run_id"], "run_123")
        self.assertEqual(manifest["artifact_paths"]["scorecard"], "D:/scorecard.json")


if __name__ == "__main__":
    unittest.main()
