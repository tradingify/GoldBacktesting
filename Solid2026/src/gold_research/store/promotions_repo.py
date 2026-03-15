"""Repository helpers for gate results and promotion state persistence."""

from contextlib import closing
from pathlib import Path
import json

from src.gold_research.store.db import get_connection, initialize_database
from src.gold_research.store.runs_repo import utc_now_iso


class PromotionsRepository:
    """Persist screening outcomes and run promotion states in SQLite."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = initialize_database(db_path)

    def upsert_gate_result(
        self,
        run_id: str,
        gate_name: str,
        status: str,
        score: float | None,
        details: dict,
    ) -> None:
        """Insert or update a gate evaluation result for a run."""
        with closing(get_connection(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO gate_results (run_id, gate_name, status, score, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, gate_name) DO UPDATE SET
                    status=excluded.status,
                    score=excluded.score,
                    details_json=excluded.details_json,
                    created_at=excluded.created_at
                """,
                (
                    run_id,
                    gate_name,
                    status,
                    score,
                    json.dumps(details, default=str),
                    utc_now_iso(),
                ),
            )
            conn.commit()

    def upsert_promotion(
        self,
        run_id: str,
        promotion_state: str,
        reason: str,
        decided_by: str = "system",
    ) -> None:
        """Insert or update the promotion state for a run."""
        with closing(get_connection(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO promotions (run_id, promotion_state, reason, decided_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    promotion_state=excluded.promotion_state,
                    reason=excluded.reason,
                    decided_by=excluded.decided_by,
                    created_at=excluded.created_at
                """,
                (run_id, promotion_state, reason, decided_by, utc_now_iso()),
            )
            conn.commit()
