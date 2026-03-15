"""Connection helpers for the research SQLite store."""

from contextlib import closing
from pathlib import Path
import sqlite3

from src.gold_research.core.paths import ProjectPaths
from src.gold_research.store.schema import SCHEMA_SQL


DB_PATH = ProjectPaths.DATA / "manifests" / "research.db"


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Apply a lightweight SQLite migration when a column is missing."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with sensible defaults for small local workloads."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: Path | None = None) -> Path:
    """Create the research database and required tables if missing."""
    path = db_path or DB_PATH
    with closing(get_connection(path)) as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_column(conn, "runs", "parent_run_id", "TEXT")
        _ensure_column(conn, "runs", "run_type", "TEXT")
        _ensure_column(conn, "runs", "fingerprint", "TEXT")
        conn.commit()
    return path
