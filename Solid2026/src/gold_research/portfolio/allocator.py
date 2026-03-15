"""Portfolio allocation helpers for multiple template styles."""

from __future__ import annotations

from typing import Iterable


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values())
    if total <= 0:
        count = len(weights)
        return {key: 1.0 / count for key in weights} if count else {}
    return {key: max(0.0, value) / total for key, value in weights.items()}


def equal_weight(run_ids: Iterable[str]) -> dict[str, float]:
    run_ids = list(run_ids)
    if not run_ids:
        return {}
    weight = 1.0 / len(run_ids)
    return {run_id: weight for run_id in run_ids}


def inverse_volatility(scorecards: dict[str, dict]) -> dict[str, float]:
    raw = {}
    for run_id, scorecard in scorecards.items():
        drawdown = abs(float(scorecard.get("max_dd_pct", 0.0)))
        raw[run_id] = 1.0 / max(drawdown, 0.01)
    return _normalize(raw)


def sharpe_tilt(scorecards: dict[str, dict]) -> dict[str, float]:
    raw = {}
    for run_id, scorecard in scorecards.items():
        raw[run_id] = max(float(scorecard.get("sharpe", 0.0)), 0.0)
    return _normalize(raw)


def family_capped(scorecards: dict[str, dict], families: dict[str, str], family_cap: float = 0.5) -> dict[str, float]:
    """Allocate by Sharpe with a cap on total family weight."""
    base = sharpe_tilt(scorecards)
    if not base:
        return {}

    family_totals: dict[str, float] = {}
    for run_id, weight in base.items():
        family = families.get(run_id, "other")
        family_totals[family] = family_totals.get(family, 0.0) + weight

    adjusted = base.copy()
    for run_id, weight in list(base.items()):
        family = families.get(run_id, "other")
        total = family_totals.get(family, weight)
        if total > family_cap:
            adjusted[run_id] = weight * (family_cap / total)
    return _normalize(adjusted)

