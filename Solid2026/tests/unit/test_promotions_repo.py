import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from src.gold_research.store.promotions_repo import PromotionsRepository


class TestPromotionsRepository(unittest.TestCase):
    def test_persists_gate_results_and_promotions(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "research.db"
            repo = PromotionsRepository(db_path)
            repo.upsert_gate_result(
                run_id="run_123",
                gate_name="screening",
                status="pass",
                score=1.0,
                details={"reason": "ok"},
            )
            repo.upsert_promotion(
                run_id="run_123",
                promotion_state="candidate_for_robustness",
                reason="Run passed all screening thresholds.",
            )

            with closing(sqlite3.connect(db_path)) as conn:
                gate_row = conn.execute(
                    "SELECT gate_name, status FROM gate_results WHERE run_id = ?",
                    ("run_123",),
                ).fetchone()
                promotion_row = conn.execute(
                    "SELECT promotion_state, reason FROM promotions WHERE run_id = ?",
                    ("run_123",),
                ).fetchone()

            self.assertEqual(gate_row[0], "screening")
            self.assertEqual(gate_row[1], "pass")
            self.assertEqual(promotion_row[0], "candidate_for_robustness")


if __name__ == "__main__":
    unittest.main()
