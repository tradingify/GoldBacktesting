import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.gold_research.portfolio.selector import CandidateRun


class TestPortfolioSmoke(unittest.TestCase):
    def test_portfolio_pipeline_persists_summary_and_members(self):
        import src.gold_research.portfolio.pipeline as pipeline_module
        import src.gold_research.store.db as store_db
        import src.gold_research.core.paths as core_paths

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_dir = root / "results"
            reports_dir = root / "reports"
            data_dir = root / "data"
            results_dir.mkdir(parents=True, exist_ok=True)
            reports_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)

            eq_a = root / "eq_a.csv"
            eq_b = root / "eq_b.csv"
            pd.DataFrame({"equity": [100000, 101000, 102500]}).to_csv(eq_a, index=False)
            pd.DataFrame({"equity": [100000, 100900, 101800]}).to_csv(eq_b, index=False)

            candidates = [
                CandidateRun(
                    run_id="run_a",
                    strategy_class_path="pkg.trend.StrategyA",
                    family="trend",
                    timeframe="5m",
                    promotion_state="candidate_for_portfolio",
                    scorecard={"sharpe": 2.1, "max_dd_pct": -0.10},
                    equity_path=eq_a,
                ),
                CandidateRun(
                    run_id="run_b",
                    strategy_class_path="pkg.mean_reversion.StrategyB",
                    family="mean_reversion",
                    timeframe="15m",
                    promotion_state="candidate_for_portfolio",
                    scorecard={"sharpe": 1.8, "max_dd_pct": -0.08},
                    equity_path=eq_b,
                ),
            ]

            original_db_path = store_db.DB_PATH
            original_results = core_paths.ProjectPaths.RESULTS
            original_data = core_paths.ProjectPaths.DATA
            original_select = pipeline_module.select_promoted_runs
            original_save = pipeline_module.PortfolioCardReport.save_report

            store_db.DB_PATH = data_dir / "manifests" / "research.db"
            core_paths.ProjectPaths.RESULTS = results_dir
            core_paths.ProjectPaths.DATA = data_dir
            pipeline_module.select_promoted_runs = lambda **kwargs: candidates
            pipeline_module.PortfolioCardReport.save_report = staticmethod(lambda portfolio_id, markdown: str(reports_dir / f"{portfolio_id}.md"))
            try:
                payload = pipeline_module.build_portfolio("PORT_SMOKE", "mixed_all_weather")
            finally:
                store_db.DB_PATH = original_db_path
                core_paths.ProjectPaths.RESULTS = original_results
                core_paths.ProjectPaths.DATA = original_data
                pipeline_module.select_promoted_runs = original_select
                pipeline_module.PortfolioCardReport.save_report = original_save

            self.assertEqual(payload["status"], "completed")
            self.assertTrue((results_dir / "portfolios" / "PORT_SMOKE" / "portfolio_summary.json").exists())

            with closing(sqlite3.connect(data_dir / "manifests" / "research.db")) as conn:
                member_count = conn.execute("SELECT COUNT(*) FROM portfolio_members WHERE portfolio_id = 'PORT_SMOKE'").fetchone()[0]
            self.assertEqual(member_count, 2)


if __name__ == "__main__":
    unittest.main()
