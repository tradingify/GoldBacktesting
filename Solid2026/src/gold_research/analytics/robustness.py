"""Robustness Aggregation."""
from typing import List, Dict, Any
from src.gold_research.analytics.scorecards import StrategyScorecard

class RobustnessAnalyzer:
    """Calculates decay and variance across multiple environmental states."""
    
    @staticmethod
    def calculate_wfo_efficiency(is_scores: List[StrategyScorecard], oos_scores: List[StrategyScorecard]) -> float:
        """
        Walk Forward Efficiency (WFE): Ratio of OOS annualized return to IS annualized return.
        WFE > 50% usually signifies a reasonably robust parameter set.
        """
        # For simplicity, returning a mathematical average ratio of Sharpe
        if not is_scores or not oos_scores:
            return 0.0
            
        avg_is_sharpe = sum(s.sharpe for s in is_scores) / len(is_scores)
        avg_oos_sharpe = sum(s.sharpe for s in oos_scores) / len(oos_scores)
        
        if avg_is_sharpe == 0:
            return 0.0
            
        return avg_oos_sharpe / avg_is_sharpe

    @staticmethod
    def evaluate_stress_decay(baseline_score: StrategyScorecard, harsh_score: StrategyScorecard) -> float:
        """
        Calculates how much PnL or Sharpe degrades when moving from Base to Harsh friction.
        """
        # Lower decay value closer to 1.0 is better (0.0 means total destruction)
        if baseline_score.sharpe <= 0:
            return 0.0
            
        return max(0.0, harsh_score.sharpe / baseline_score.sharpe)

    @staticmethod
    def summarize_stress_suite(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize multi-profile stress execution using stored scorecards."""
        scorecards = {
            item["stress_profile"]: StrategyScorecard(**item["scorecard"])
            for item in results
            if item.get("scorecard")
        }
        base_score = scorecards.get("base") or scorecards.get("optimistic")
        harsh_score = scorecards.get("harsh")
        stress_decay = 0.0
        if base_score and harsh_score:
            stress_decay = RobustnessAnalyzer.evaluate_stress_decay(base_score, harsh_score)
        return {
            "profiles": list(scorecards.keys()),
            "stress_decay": stress_decay,
            "baseline_run_id": base_score.run_id if base_score else None,
            "harsh_run_id": harsh_score.run_id if harsh_score else None,
        }

    @staticmethod
    def summarize_walkforward(is_results: List[Dict[str, Any]], oos_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize walk-forward execution using child-run scorecards."""
        is_scores = [StrategyScorecard(**item["scorecard"]) for item in is_results if item.get("scorecard")]
        oos_scores = [StrategyScorecard(**item["scorecard"]) for item in oos_results if item.get("scorecard")]
        return {
            "folds": len(oos_results),
            "wfo_efficiency": RobustnessAnalyzer.calculate_wfo_efficiency(is_scores, oos_scores),
            "is_run_ids": [score.run_id for score in is_scores],
            "oos_run_ids": [score.run_id for score in oos_scores],
        }
