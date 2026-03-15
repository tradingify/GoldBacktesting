"""
Regime Performance Analysis.

Segregates strategy performance into distinct buckets 
(e.g., High Volatility vs Low Volatility environments) to identify
structural weaknesses in the edge.
"""
import pandas as pd
from typing import Dict, Any

class RegimeAnalyzer:
    
    @staticmethod
    def attach_volatility_regime(returns: pd.Series, lookback: int = 20) -> pd.DataFrame:
        """
        Calculates rolling standard deviation of daily returns to classify
        each day as 'High Vol' or 'Low Vol' based on being above/below
        the median historic volatility.
        """
        df = returns.to_frame(name="returns")
        df["vol_horizon"] = df["returns"].rolling(lookback).std()
        
        median_vol = df["vol_horizon"].median()
        
        df["regime"] = "LOW_VOL"
        df.loc[df["vol_horizon"] > median_vol, "regime"] = "HIGH_VOL"
        
        return df
        
    @staticmethod
    def break_down_performance(returns_with_regime: pd.DataFrame) -> Dict[str, float]:
        """
        Groups the returns by the 'regime' column and computes Sharpe
        or simple sums for each independent environment.
        """
        if returns_with_regime.empty or "regime" not in returns_with_regime.columns:
            return {}
            
        summary = {}
        grouped = returns_with_regime.groupby("regime")
        
        for regime_name, group in grouped:
             # Basic annualized return proxy (assumes daily data for this scaffold)
             ann_ret = group["returns"].mean() * 252
             summary[f"{regime_name}_annual_return"] = ann_ret
             
        return summary