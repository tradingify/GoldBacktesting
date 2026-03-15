import unittest
import pandas as pd
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import closing
import sqlite3
from src.gold_research.data.datasets.manifest import DatasetManifest
from src.gold_research.data.datasets.registry import DatasetRegistry

class TestRegistry(unittest.TestCase):
    def test_manifest_creation_and_registry(self):
        # Create mock data
        df = pd.DataFrame({
            "datetime": [pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-01-02", tz="UTC")],
            "close": [1900.0, 1910.0]
        })
        
        # 1. Create Manifest
        m = DatasetManifest.create_from_dataframe(
            df=df,
            dataset_id="test_gold_1d",
            source="ibkr",
            instrument="XAUUSD",
            timeframe="1d",
            notes="Mock data for testing."
        )
        
        self.assertEqual(m.dataset_id, "test_gold_1d")
        self.assertEqual(m.row_count, 2)
        self.assertIsNotNone(m.checksum)
        self.assertIn("datetime", m.schema)
        
        # 2. Test Registry Operations
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry = DatasetRegistry(manifests_dir=root / "manifests", db_path=root / "research.db")
            
            # Save
            path = registry.register(m)
            self.assertTrue(path.exists())
            
            # Load
            loaded_m = registry.get_manifest("test_gold_1d")
            self.assertIsNotNone(loaded_m)
            self.assertEqual(loaded_m.checksum, m.checksum)
            
            # List
            datasets = registry.list_datasets()
            self.assertIn("test_gold_1d", datasets)

            with closing(sqlite3.connect(root / "research.db")) as conn:
                row = conn.execute(
                    "SELECT dataset_id, checksum FROM datasets WHERE dataset_id = ?",
                    ("test_gold_1d",),
                ).fetchone()
            self.assertEqual(row[0], "test_gold_1d")
            self.assertEqual(row[1], m.checksum)

    def test_manifest_creation_from_parquet(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            parquet_path = root / "xauusd_15_mins.parquet"
            df = pd.DataFrame({
                "datetime": [pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-01-02", tz="UTC")],
                "open": [1900.0, 1905.0],
                "high": [1902.0, 1907.0],
                "low": [1899.0, 1904.0],
                "close": [1901.0, 1906.0],
                "volume": [10, 12],
            })
            df.to_parquet(parquet_path)

            manifest = DatasetManifest.create_from_parquet(
                parquet_path=parquet_path,
                dataset_id="xauusd_15_mins",
                source="ibkr",
                instrument="XAUUSD",
                timeframe="15m",
            )

            self.assertEqual(manifest.dataset_id, "xauusd_15_mins")
            self.assertEqual(manifest.source_files[0]["path"], str(parquet_path))
            self.assertEqual(manifest.build_recipe["builder"], "create_from_parquet")

if __name__ == '__main__':
    unittest.main()
