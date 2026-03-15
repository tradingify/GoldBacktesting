"""Repository helpers for dataset manifest persistence."""

from contextlib import closing
from pathlib import Path

from src.gold_research.data.datasets.manifest import DatasetManifest
from src.gold_research.store.db import get_connection, initialize_database


class DatasetsRepository:
    """Persist registered datasets alongside manifest JSON files."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = initialize_database(db_path)

    def upsert_dataset(self, manifest: DatasetManifest, manifest_path: Path) -> None:
        """Insert or update a dataset record from its manifest metadata."""
        with closing(get_connection(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO datasets (
                    dataset_id,
                    source,
                    instrument,
                    timeframe,
                    checksum,
                    row_count,
                    min_timestamp,
                    max_timestamp,
                    manifest_path,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    source=excluded.source,
                    instrument=excluded.instrument,
                    timeframe=excluded.timeframe,
                    checksum=excluded.checksum,
                    row_count=excluded.row_count,
                    min_timestamp=excluded.min_timestamp,
                    max_timestamp=excluded.max_timestamp,
                    manifest_path=excluded.manifest_path,
                    created_at=excluded.created_at
                """,
                (
                    manifest.dataset_id,
                    manifest.source,
                    manifest.instrument,
                    manifest.timeframe,
                    manifest.checksum,
                    manifest.row_count,
                    manifest.min_timestamp,
                    manifest.max_timestamp,
                    str(manifest_path),
                    manifest.creation_timestamp,
                ),
            )
            conn.commit()
