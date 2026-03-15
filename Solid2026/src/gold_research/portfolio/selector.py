"""Select promoted runs for portfolio construction."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import json

from src.gold_research.core.paths import ProjectPaths
from src.gold_research.store.db import get_connection


@dataclass
class CandidateRun:
    """Normalized view of a promoted run eligible for portfolio assembly."""

    run_id: str
    strategy_class_path: str
    family: str
    timeframe: str | None
    promotion_state: str
    scorecard: dict
    equity_path: Path | None


def infer_family(strategy_class_path: str) -> str:
    """Infer a strategy family from the class path."""
    parts = strategy_class_path.split(".")
    if "mean_reversion" in parts:
        return "mean_reversion"
    if "trend" in parts:
        return "trend"
    if "breakout" in parts:
        return "breakout"
    if "pullback" in parts:
        return "pullback"
    if "smc" in parts or "ict" in parts:
        return "smc"
    if "session" in parts:
        return "session"
    if "hybrid" in parts:
        return "hybrid"
    return "other"


def _read_scorecard(run_row: dict) -> tuple[dict, Path | None]:
    """Load scorecard and equity artifact from the canonical run directory."""
    run_dir = ProjectPaths.RESULTS / "raw_runs" / run_row["experiment_id"] / run_row["run_id"]
    scorecard_path = run_dir / "scorecard.json"
    if not scorecard_path.exists():
        return {}, None
    with open(scorecard_path, "r", encoding="utf-8") as handle:
        scorecard = json.load(handle)
    equity_path = run_dir / "equity.csv"
    return scorecard, (equity_path if equity_path.exists() else None)


def select_promoted_runs(
    *,
    promotion_states: tuple[str, ...] = ("candidate_for_portfolio", "candidate_for_robustness", "hold_for_review"),
    families: set[str] | None = None,
) -> list[CandidateRun]:
    """Load promoted runs from SQLite and filter them into candidate records."""
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT runs.run_id, runs.experiment_id, runs.strategy_class_path, runs.timeframe, promotions.promotion_state
            FROM runs
            JOIN promotions ON promotions.run_id = runs.run_id
            WHERE promotions.promotion_state IN ({placeholders})
            ORDER BY promotions.created_at DESC
            """.format(placeholders=", ".join(["?"] * len(promotion_states))),
            promotion_states,
        ).fetchall()

    candidates: list[CandidateRun] = []
    for row in rows:
        row_dict = dict(row)
        family = infer_family(row_dict["strategy_class_path"])
        if families and family not in families:
            continue
        scorecard, equity_path = _read_scorecard(row_dict)
        if not scorecard:
            continue
        candidates.append(
            CandidateRun(
                run_id=row_dict["run_id"],
                strategy_class_path=row_dict["strategy_class_path"],
                family=family,
                timeframe=row_dict["timeframe"],
                promotion_state=row_dict["promotion_state"],
                scorecard=scorecard,
                equity_path=equity_path,
            )
        )
    return candidates
