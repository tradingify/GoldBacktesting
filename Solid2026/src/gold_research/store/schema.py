"""Schema management for the research SQLite store."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    checksum TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    min_timestamp TEXT NOT NULL,
    max_timestamp TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    parent_run_id TEXT,
    run_type TEXT,
    fingerprint TEXT,
    status TEXT NOT NULL,
    strategy_class_path TEXT NOT NULL,
    dataset_manifest_id TEXT NOT NULL,
    timeframe TEXT,
    started_at TEXT,
    completed_at TEXT,
    error_text TEXT
);

CREATE TABLE IF NOT EXISTS run_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    experiment_id TEXT NOT NULL,
    parent_run_id TEXT,
    run_type TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    spec_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, artifact_type, path)
);

CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    gate_name TEXT NOT NULL,
    status TEXT NOT NULL,
    score REAL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, gate_name)
);

CREATE TABLE IF NOT EXISTS promotions (
    run_id TEXT PRIMARY KEY,
    promotion_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id TEXT PRIMARY KEY,
    portfolio_type TEXT NOT NULL,
    selection_policy_json TEXT NOT NULL,
    allocation_policy_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    weight REAL NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(portfolio_id, run_id)
);
"""
