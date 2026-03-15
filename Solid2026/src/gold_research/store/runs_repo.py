"""Repository helpers for tracking run lifecycle state."""

from contextlib import closing
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterable

from src.gold_research.store.db import get_connection, initialize_database


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp string."""
    return datetime.now(UTC).isoformat()


class RunsRepository:
    """Minimal persistence layer for run state and artifact bookkeeping."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = initialize_database(db_path)

    def upsert_run(
        self,
        run_id: str,
        experiment_id: str,
        status: str,
        strategy_class_path: str,
        dataset_manifest_id: str,
        parent_run_id: str | None = None,
        run_type: str | None = None,
        fingerprint: str | None = None,
        timeframe: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        error_text: str | None = None,
    ) -> None:
        """Insert or update the current lifecycle state for a run."""
        with closing(get_connection(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id,
                    experiment_id,
                    parent_run_id,
                    run_type,
                    fingerprint,
                    status,
                    strategy_class_path,
                    dataset_manifest_id,
                    timeframe,
                    started_at,
                    completed_at,
                    error_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    experiment_id=excluded.experiment_id,
                    parent_run_id=COALESCE(runs.parent_run_id, excluded.parent_run_id),
                    run_type=COALESCE(runs.run_type, excluded.run_type),
                    fingerprint=COALESCE(runs.fingerprint, excluded.fingerprint),
                    status=excluded.status,
                    strategy_class_path=excluded.strategy_class_path,
                    dataset_manifest_id=excluded.dataset_manifest_id,
                    timeframe=excluded.timeframe,
                    started_at=COALESCE(runs.started_at, excluded.started_at),
                    completed_at=excluded.completed_at,
                    error_text=excluded.error_text
                """,
                (
                    run_id,
                    experiment_id,
                    parent_run_id,
                    run_type,
                    fingerprint,
                    status,
                    strategy_class_path,
                    dataset_manifest_id,
                    timeframe,
                    started_at,
                    completed_at,
                    error_text,
                ),
            )
            conn.commit()

    def record_artifacts(self, run_id: str, artifacts: Iterable[tuple[str, str]]) -> None:
        """Persist artifact paths for a completed or failed run."""
        created_at = utc_now_iso()
        with closing(get_connection(self.db_path)) as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO run_artifacts (run_id, artifact_type, path, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [(run_id, artifact_type, path, created_at) for artifact_type, path in artifacts],
            )
            conn.commit()
