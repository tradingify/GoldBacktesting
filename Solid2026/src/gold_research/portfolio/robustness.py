"""Portfolio robustness diagnostics."""

from __future__ import annotations

import pandas as pd

from src.gold_research.analytics.portfolio import PortfolioComposer


def leave_one_out_metrics(equity_curves: pd.DataFrame) -> dict[str, dict]:
    """Measure portfolio metrics after removing each constituent in turn."""
    results: dict[str, dict] = {}
    for column in equity_curves.columns:
        reduced = equity_curves.drop(columns=[column])
        synthetic = PortfolioComposer.synthesize_weighted_equity(reduced)
        results[column] = PortfolioComposer.compute_portfolio_metrics(synthetic)
    return results


def weight_perturbation_metrics(equity_curves: pd.DataFrame, base_weights: dict[str, float], bump: float = 0.1) -> dict[str, dict]:
    """Measure sensitivity by overweighting each constituent by a small bump."""
    results: dict[str, dict] = {}
    for column in equity_curves.columns:
        weights = base_weights.copy()
        weights[column] = weights.get(column, 0.0) + bump
        total = sum(weights.values())
        weights = {key: value / total for key, value in weights.items()}
        synthetic = PortfolioComposer.synthesize_weighted_equity(equity_curves, weights=weights)
        results[column] = PortfolioComposer.compute_portfolio_metrics(synthetic)
    return results

