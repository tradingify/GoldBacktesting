"""Helpers for writing run artifacts with a consistent layout."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from src.gold_research.core.paths import ProjectPaths


def get_run_dir(experiment_id: str, run_id: str) -> Path:
    """Return the canonical directory for a specific run."""
    path = ProjectPaths.RESULTS / "raw_runs" / experiment_id / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write a JSON artifact to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, default=str)
    return path


def write_dataframe_csv(path: Path, frame: pd.DataFrame) -> Path | None:
    """Write a DataFrame artifact when content is available."""
    if frame.empty:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=True)
    return path


def build_run_manifest(
    *,
    run_id: str,
    experiment_id: str,
    dataset_manifest_id: str,
    strategy_class_path: str,
    strategy_params: dict[str, Any],
    timeframe: str | None,
    status: str,
    artifact_paths: dict[str, str],
    error_text: str | None = None,
) -> dict[str, Any]:
    """Build a compact JSON-serializable manifest describing the run output."""
    return {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "dataset_manifest_id": dataset_manifest_id,
        "strategy_class_path": strategy_class_path,
        "strategy_params": strategy_params,
        "timeframe": timeframe,
        "status": status,
        "artifact_paths": artifact_paths,
        "error_text": error_text,
    }

