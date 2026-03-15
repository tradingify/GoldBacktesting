import unittest

from src.gold_research.analytics.scorecards import StrategyScorecard
from src.gold_research.gates.screening import evaluate_screening


class TestScreeningGate(unittest.TestCase):
    def test_screening_passes_strong_run(self):
        decision = evaluate_screening(
            StrategyScorecard(
                run_id="run_pass",
                total_trades=500,
                win_rate=0.55,
                profit_factor=1.8,
                total_net_profit=12000.0,
                sharpe=2.1,
                sortino=2.5,
                calmar=1.1,
                max_dd_pct=-0.10,
                status="COMPLETED",
            )
        )

        self.assertEqual(decision.status, "pass")
        self.assertEqual(decision.promotion_state, "candidate_for_robustness")

    def test_screening_soft_fails_partial_run(self):
        decision = evaluate_screening(
            StrategyScorecard(
                run_id="run_soft_fail",
                total_trades=250,
                win_rate=0.52,
                profit_factor=1.25,
                total_net_profit=3000.0,
                sharpe=1.2,
                sortino=1.5,
                calmar=0.8,
                max_dd_pct=-0.12,
                status="COMPLETED",
            )
        )

        self.assertEqual(decision.status, "soft_fail")
        self.assertEqual(decision.promotion_state, "hold_for_review")

    def test_screening_rejects_failed_run(self):
        decision = evaluate_screening(
            StrategyScorecard(
                run_id="run_fail",
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                total_net_profit=0.0,
                sharpe=0.0,
                sortino=0.0,
                calmar=0.0,
                max_dd_pct=0.0,
                status="FAILED",
            )
        )

        self.assertEqual(decision.status, "hard_fail")
        self.assertEqual(decision.promotion_state, "rejected")


if __name__ == "__main__":
    unittest.main()

