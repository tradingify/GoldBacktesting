import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.gold_research.portfolio.allocator import equal_weight, family_capped, inverse_volatility, sharpe_tilt
from src.gold_research.portfolio.selector import CandidateRun
from src.gold_research.store.portfolio_repo import PortfolioRepository


class TestPortfolioFactory(unittest.TestCase):
    def test_allocators_return_normalized_weights(self):
        scorecards = {
            "run_a": {"sharpe": 2.0, "max_dd_pct": -0.10},
            "run_b": {"sharpe": 1.0, "max_dd_pct": -0.20},
        }
        families = {"run_a": "trend", "run_b": "trend"}

        self.assertAlmostEqual(sum(equal_weight(scorecards.keys()).values()), 1.0)
        self.assertAlmostEqual(sum(inverse_volatility(scorecards).values()), 1.0)
        self.assertAlmostEqual(sum(sharpe_tilt(scorecards).values()), 1.0)
        self.assertAlmostEqual(sum(family_capped(scorecards, families).values()), 1.0)

    def test_portfolio_repository_persists_portfolio_and_members(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "research.db"
            repo = PortfolioRepository(db_path)
            repo.upsert_portfolio(
                portfolio_id="PORT_01",
                portfolio_type="mixed_all_weather",
                selection_policy={"families": "all"},
                allocation_policy={"allocator": "family_capped"},
            )
            repo.replace_members(
                "PORT_01",
                [
                    {"run_id": "run_a", "weight": 0.6, "role": "trend"},
                    {"run_id": "run_b", "weight": 0.4, "role": "mean_reversion"},
                ],
            )

            with closing(sqlite3.connect(db_path)) as conn:
                portfolio_row = conn.execute(
                    "SELECT portfolio_type FROM portfolios WHERE portfolio_id = ?",
                    ("PORT_01",),
                ).fetchone()
                member_count = conn.execute(
                    "SELECT COUNT(*) FROM portfolio_members WHERE portfolio_id = ?",
                    ("PORT_01",),
                ).fetchone()[0]

            self.assertEqual(portfolio_row[0], "mixed_all_weather")
            self.assertEqual(member_count, 2)

    def test_build_portfolio_pipeline_with_stubbed_candidates(self):
        import src.gold_research.portfolio.pipeline as pipeline_module

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_dir = root / "results"
            reports_dir = root / "reports"
            results_dir.mkdir(parents=True, exist_ok=True)
            reports_dir.mkdir(parents=True, exist_ok=True)

            run_a_equity = root / "run_a_equity.csv"
            run_b_equity = root / "run_b_equity.csv"
            pd.DataFrame({"equity": [100000, 101000, 102000]}).to_csv(run_a_equity, index=False)
            pd.DataFrame({"equity": [100000, 100500, 101500]}).to_csv(run_b_equity, index=False)

            candidates = [
                CandidateRun(
                    run_id="run_a",
                    strategy_class_path="pkg.trend.StrategyA",
                    family="trend",
                    timeframe="5m",
                    promotion_state="candidate_for_portfolio",
                    scorecard={"sharpe": 2.0, "max_dd_pct": -0.10},
                    equity_path=run_a_equity,
                ),
                CandidateRun(
                    run_id="run_b",
                    strategy_class_path="pkg.mean_reversion.StrategyB",
                    family="mean_reversion",
                    timeframe="15m",
                    promotion_state="candidate_for_portfolio",
                    scorecard={"sharpe": 1.5, "max_dd_pct": -0.08},
                    equity_path=run_b_equity,
                ),
            ]

            original_select = pipeline_module.select_promoted_runs
            original_repo = pipeline_module.PortfolioRepository
            original_save = pipeline_module.PortfolioCardReport.save_report
            original_results = pipeline_module.ProjectPaths.RESULTS

            class TempPortfolioRepository(PortfolioRepository):
                def __init__(self):
                    super().__init__(root / "research.db")

            pipeline_module.select_promoted_runs = lambda **kwargs: candidates
            pipeline_module.PortfolioRepository = TempPortfolioRepository
            pipeline_module.PortfolioCardReport.save_report = staticmethod(lambda portfolio_id, markdown: str(reports_dir / f"{portfolio_id}.md"))
            pipeline_module.ProjectPaths.RESULTS = results_dir
            try:
                payload = pipeline_module.build_portfolio("PORT_TEST", "mixed_all_weather")
            finally:
                pipeline_module.select_promoted_runs = original_select
                pipeline_module.PortfolioRepository = original_repo
                pipeline_module.PortfolioCardReport.save_report = original_save
                pipeline_module.ProjectPaths.RESULTS = original_results

            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["member_count"], 2)
            self.assertIn("metrics", payload)
            self.assertTrue((results_dir / "portfolios" / "PORT_TEST" / "portfolio_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
