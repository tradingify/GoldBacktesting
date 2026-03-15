"""Repository helpers for queued batch run execution."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json

from src.gold_research.store.db import get_connection, initialize_database
from src.gold_research.store.runs_repo import utc_now_iso


class QueueRepository:
    """Persist queued child runs for grid and random search execution."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = initialize_database(db_path)

    def enqueue(
        self,
        *,
        run_id: str,
        experiment_id: str,
        parent_run_id: str | None,
        run_type: str,
        fingerprint: str,
        spec_json: dict,
    ) -> bool:
        """Insert a queued run if its fingerprint has not already been scheduled."""
        now = utc_now_iso()
        with closing(get_connection(self.db_path)) as conn:
            existing = conn.execute(
                "SELECT run_id FROM run_queue WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing:
                return False

            existing_run = conn.execute(
                "SELECT run_id FROM runs WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing_run:
                return False

            conn.execute(
                """
                INSERT INTO run_queue (
                    run_id, experiment_id, parent_run_id, run_type, fingerprint,
                    spec_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    experiment_id,
                    parent_run_id,
                    run_type,
                    fingerprint,
                    json.dumps(spec_json, default=str),
                    "queued",
                    now,
                    now,
                ),
            )
            conn.commit()
            return True

    def list_by_status(self, status: str, experiment_id: str | None = None) -> list[dict]:
        """Return queued run payloads, optionally limited to one experiment."""
        with closing(get_connection(self.db_path)) as conn:
            if experiment_id is None:
                rows = conn.execute(
                    "SELECT * FROM run_queue WHERE status = ? ORDER BY id",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM run_queue WHERE status = ? AND experiment_id = ? ORDER BY id",
                    (status, experiment_id),
                ).fetchall()
        return [dict(row) for row in rows]

    def update_status(self, run_id: str, status: str) -> None:
        """Update the queue state for a run."""
        with closing(get_connection(self.db_path)) as conn:
            conn.execute(
                "UPDATE run_queue SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, utc_now_iso(), run_id),
            )
            conn.commit()

