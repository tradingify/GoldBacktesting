"""
Sensitivity and Parameter Surface Analysis.

Tools to visualize or evaluate how rapidly output metrics change
in response to tiny shifts in input parameters (i.e., looking for
flat parameter plateaus vs sharp, brittle peaks).
"""
import pandas as pd
from typing import List, Dict, Any

class SensitivityAnalysis:
    """Evaluates the surrounding grid neighborhood of a parameter set."""
    
    @staticmethod
    def construct_surface(grid_results: List[Dict[str, Any]], target_metric: str = "sharpe") -> pd.DataFrame:
        """
        Converts raw grid outputs into a flat DataFrame mapping input params
        to the resulting metric for easy correlation or heatmap generation.
        """
        records = []
        for res in grid_results:
            row = {}
            if "strategy_params" in res:
                 row.update(res["strategy_params"])
            if "scorecard" in res:
                 row[target_metric] = getattr(res["scorecard"], target_metric, 0.0)
            records.append(row)
            
        return pd.DataFrame(records)
        
    @staticmethod
    def measure_ruggedness(surface_df: pd.DataFrame, target_metric: str = "sharpe") -> float:
        """
        Proxy for parameter stability. High standard deviation of adjacent
        parameters means a rugged, overfit landscape.
        """
        # A simple stub metric: coefficient of variation of the target metric
        # across the entire sampled space.
        if target_metric not in surface_df.columns or len(surface_df) < 2:
            return 0.0
            
        mean_perf = surface_df[target_metric].mean()
        std_perf = surface_df[target_metric].std()
        
        if mean_perf == 0:
             return float('inf')
             
        # CV: Lower is more stable (flatter plateau)
        return std_perf / abs(mean_perf)