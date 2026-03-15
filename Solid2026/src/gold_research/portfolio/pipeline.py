"""Canonical portfolio assembly pipeline."""

from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from src.gold_research.analytics.clustering import ClusteringAnalyzer
from src.gold_research.analytics.portfolio import PortfolioComposer
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.portfolio.allocator import equal_weight, family_capped, inverse_volatility, sharpe_tilt
from src.gold_research.portfolio.robustness import leave_one_out_metrics, weight_perturbation_metrics
from src.gold_research.portfolio.selector import select_promoted_runs
from src.gold_research.portfolio.templates import PORTFOLIO_TEMPLATES
from src.gold_research.reports.portfolio_card import PortfolioCardReport
from src.gold_research.store.portfolio_repo import PortfolioRepository


ALLOCATORS = {
    "equal_weight": equal_weight,
    "inverse_volatility": inverse_volatility,
    "sharpe_tilt": sharpe_tilt,
    "family_capped": family_capped,
}


def _load_equity_frame(candidates: list) -> pd.DataFrame:
    frames = []
    for candidate in candidates:
        if candidate.equity_path is None:
            continue
        frame = pd.read_csv(candidate.equity_path)
        if "equity" not in frame.columns:
            continue
        series = frame["equity"].astype(float).rename(candidate.run_id)
        frames.append(series.reset_index(drop=True))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).dropna()


def build_portfolio(portfolio_id: str, template_name: str) -> dict:
    """Construct a portfolio from promoted runs using a named template."""
    if template_name not in PORTFOLIO_TEMPLATES:
        raise ValueError(f"Unknown portfolio template: {template_name}")

    template = PORTFOLIO_TEMPLATES[template_name]
    candidates = select_promoted_runs(families=template["families"])
    if not candidates:
        return {
            "portfolio_id": portfolio_id,
            "template": template_name,
            "status": "empty",
            "members": [],
        }

    scorecards = {candidate.run_id: candidate.scorecard for candidate in candidates}
    families = {candidate.run_id: candidate.family for candidate in candidates}
    allocator_name = template["allocator"]
    if allocator_name == "family_capped":
        weights = family_capped(scorecards, families)
    elif allocator_name == "inverse_volatility":
        weights = inverse_volatility(scorecards)
    elif allocator_name == "sharpe_tilt":
        weights = sharpe_tilt(scorecards)
    else:
        weights = equal_weight(scorecards.keys())

    equity_frame = _load_equity_frame(candidates)
    synthetic_equity = PortfolioComposer.synthesize_weighted_equity(equity_frame, weights=weights)
    metrics = PortfolioComposer.compute_portfolio_metrics(synthetic_equity)
    returns_df = equity_frame.pct_change().dropna() if not equity_frame.empty else pd.DataFrame()
    corr_matrix = ClusteringAnalyzer.compute_correlation_matrix(returns_df)
    high_corr_pairs = ClusteringAnalyzer.find_highly_correlated_pairs(corr_matrix, threshold=0.70) if not corr_matrix.empty else []
    robustness = {
        "leave_one_out": leave_one_out_metrics(equity_frame) if not equity_frame.empty else {},
        "weight_perturbation": weight_perturbation_metrics(equity_frame, weights) if not equity_frame.empty else {},
        "high_correlation_pairs": high_corr_pairs,
    }

    members = [
        {
            "run_id": candidate.run_id,
            "weight": weights.get(candidate.run_id, 0.0),
            "role": candidate.family,
        }
        for candidate in candidates
        if candidate.run_id in weights
    ]

    repo = PortfolioRepository()
    repo.upsert_portfolio(
        portfolio_id=portfolio_id,
        portfolio_type=template_name,
        selection_policy={"families": sorted(template["families"]) if template["families"] else "all"},
        allocation_policy={"allocator": allocator_name},
    )
    repo.replace_members(portfolio_id, members)

    results_dir = ProjectPaths.RESULTS / "portfolios" / portfolio_id
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "portfolio_id": portfolio_id,
        "template": template_name,
        "status": "completed",
        "member_count": len(members),
        "members": members,
        "metrics": metrics,
        "robustness": robustness,
    }
    with open(results_dir / "portfolio_summary.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, default=str)

    markdown = PortfolioCardReport.generate_markdown(
        portfolio_id,
        metrics,
        [member["run_id"] for member in members],
    )
    report_path = PortfolioCardReport.save_report(portfolio_id, markdown)
    payload["report_path"] = report_path
    return payload
