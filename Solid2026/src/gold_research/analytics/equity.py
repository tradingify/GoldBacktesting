"""
Equity Curve Diagnostics.

Granular inspection of the portfolio account balance mapping, identifying
the longest holding periods underwater or the steepest runups.
"""
import pandas as pd
from typing import Dict, Any

class EquityAnalyzer:
    
    @staticmethod
    def compute_underwater_blocks(equity_curve: pd.Series) -> pd.DataFrame:
        """
        Identifies exactly when drawdowns start and end, and calculates
        their total time-to-recovery (TTR) duration.
        """
        rolling_max = equity_curve.cummax()
        drawdowns = (equity_curve - rolling_max) / rolling_max
        
        # Mark blocks where we are NOT at a new ATH
        is_underwater = drawdowns < 0.0
        
        # A simple state machine to find blocks. Here mapped elegantly with pandas
        # groupings where 'not underwater' boundary increments a block ID.
        blocks = (~is_underwater).cumsum()
        
        underwater_periods = []
        
        # Group by the block ID
        for _, group in drawdowns[is_underwater].groupby(blocks):
             if len(group) == 0:
                 continue
                 
             start_idx = group.index[0]
             end_idx = group.index[-1]
             duration = len(group)
             max_depth = group.min()
             
             underwater_periods.append({
                 "start": start_idx,
                 "end": end_idx,
                 "duration_bars": duration,
                 "max_depth_pct": max_depth
             })
             
        return pd.DataFrame(underwater_periods)
        
    @staticmethod
    def maximum_underwater_duration(equity_curve: pd.Series) -> int:
        """Returns the longest continuous period (in bars) without a new high."""
        df = EquityAnalyzer.compute_underwater_blocks(equity_curve)
        if df.empty:
            return 0
        return int(df["duration_bars"].max())