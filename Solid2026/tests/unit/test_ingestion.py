import unittest
import pandas as pd
from datetime import datetime
from src.gold_research.data.ingest.ib_loader import _parse_datetime
from src.gold_research.data.ingest.normalize import normalize_candles

class TestIngestion(unittest.TestCase):

    def test_parse_datetime_formats(self):
        """Test IBKR datetime string parsing across various known formats."""
        
        # Format 1: Full timestamp with timezone
        dt1 = _parse_datetime("20250225 18:00:00 US/Eastern")
        self.assertEqual(str(dt1.tz), "UTC")
        self.assertEqual(dt1.hour, 23) # Eastern 18:00 is UTC 23:00

        # Format 2: No timezone (double space)
        dt2 = _parse_datetime("20250227  15:00:00")
        self.assertEqual(str(dt2.tz), "UTC")
        self.assertEqual(dt2.hour, 15)

        # Format 3: Date only
        dt3 = _parse_datetime("20240304")
        self.assertEqual(str(dt3.tz), "UTC")
        self.assertEqual(dt3.hour, 0)

    def test_normalize_schema(self):
        """Test normalization and sorting of candles."""
        
        raw_data = {
            "datetime": [ pd.Timestamp("2023-01-02", tz="UTC"), pd.Timestamp("2023-01-01", tz="UTC") ],
            "open": ["1900", "1890"],  # Test casting
            "high": [1905.0, 1895.5],
            "low": [1898.0, 1888.0],
            "close": [1902.0, 1892.0]
        }
        df = pd.DataFrame(raw_data)
        
        clean_df = normalize_candles(df)
        
        # Verify columns exist
        self.assertIn("volume", clean_df.columns)
        self.assertEqual(clean_df["volume"].iloc[0], 0, "Volume should default to 0 for Spot Gold")
        
        # Verify ordering is preserved/fixed
        self.assertTrue(clean_df["datetime"].iloc[0] < clean_df["datetime"].iloc[1])
        
        # Verify types
        self.assertTrue(pd.api.types.is_float_dtype(clean_df["open"]))

    def test_normalize_missing_cols(self):
        """Test exception raised on missing columns."""
        df = pd.DataFrame({"datetime": [pd.Timestamp("2023-01-01")], "open": [1900]})
        with self.assertRaises(ValueError):
            normalize_candles(df)

if __name__ == '__main__':
    unittest.main()
