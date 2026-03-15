"""Discovery-stage screening gate driven by project evaluation thresholds."""

from __future__ import annotations

from dataclasses import dataclass

from src.gold_research.analytics.scorecards import StrategyScorecard
from src.gold_research.core.config import load_yaml
from src.gold_research.core.paths import ProjectPaths


@dataclass
class GateDecision:
    """Structured outcome for a single gate evaluation."""

    gate_name: str
    status: str
    score: float
    promotion_state: str
    reason: str
    details: dict


def _screening_thresholds() -> dict:
    """Load the discovery screening thresholds from project config."""
    config = load_yaml(ProjectPaths.CONFIG_GLOBAL / "evaluation.yaml")
    thresholds = config.get("promotion_thresholds", {}).get("candidate_for_robustness", {})
    return {
        "min_sharpe": float(thresholds.get("min_sharpe", 1.5)),
        "min_trades": int(thresholds.get("min_trades", 150)),
        "min_profit_factor": float(thresholds.get("min_profit_factor", 1.2)),
        "max_drawdown": float(thresholds.get("max_drawdown", 0.15)),
    }


def evaluate_screening(scorecard: StrategyScorecard) -> GateDecision:
    """Evaluate whether a completed discovery run deserves deeper robustness work."""
    thresholds = _screening_thresholds()

    checks = {
        "min_sharpe": scorecard.sharpe >= thresholds["min_sharpe"],
        "min_trades": scorecard.total_trades >= thresholds["min_trades"],
        "min_profit_factor": scorecard.profit_factor >= thresholds["min_profit_factor"],
        "max_drawdown": abs(scorecard.max_dd_pct) <= thresholds["max_drawdown"],
        "completed_status": scorecard.status == "COMPLETED",
    }

    passed_checks = sum(1 for passed in checks.values() if passed)
    score = passed_checks / len(checks)

    if scorecard.status == "FAILED":
        return GateDecision(
            gate_name="screening",
            status="hard_fail",
            score=0.0,
            promotion_state="rejected",
            reason="Run failed before screening could be completed.",
            details={"thresholds": thresholds, "checks": checks},
        )

    if all(checks.values()):
        return GateDecision(
            gate_name="screening",
            status="pass",
            score=score,
            promotion_state="candidate_for_robustness",
            reason="Run passed all discovery screening thresholds.",
            details={"thresholds": thresholds, "checks": checks},
        )

    if checks["completed_status"] and passed_checks >= 3:
        return GateDecision(
            gate_name="screening",
            status="soft_fail",
            score=score,
            promotion_state="hold_for_review",
            reason="Run passed some but not all screening thresholds.",
            details={"thresholds": thresholds, "checks": checks},
        )

    return GateDecision(
        gate_name="screening",
        status="hard_fail",
        score=score,
        promotion_state="rejected",
        reason="Run did not meet the minimum discovery screening thresholds.",
        details={"thresholds": thresholds, "checks": checks},
    )
