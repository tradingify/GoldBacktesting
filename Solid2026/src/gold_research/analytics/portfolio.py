"""
Portfolio Level Aggregator.

Rolls up the metrics of several individual Strategy backtest tracks assuming
they were executed concurrently on the same capital base.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List

from src.gold_research.analytics.metrics import sharpe_ratio, max_drawdown

class PortfolioComposer:
    
    @staticmethod
    def synthesize_equity(equity_curves_df: pd.DataFrame, initial_capital: float = 100000.0) -> pd.Series:
        """
        Given a DataFrame of N equity curves (in absolute dollar value) starting from 
        the same baseline, calculates the netted aggregate portfolio value.
        """
        if equity_curves_df.empty:
            return pd.Series(dtype=float)
            
        # N strategies all starting at $100k implies $N*100k total gross value.
        # Here we isolate the PnL of each, sum the PnL, and apply to 1 global account.
        
        # Absolute PnL for each strategy over time
        pnl_matrix = equity_curves_df - initial_capital
        
        # Aggregate Net PnL 
        total_pnl = pnl_matrix.sum(axis=1)
        
        # Global Account Value
        return initial_capital + total_pnl

    @staticmethod
    def synthesize_weighted_equity(
        equity_curves_df: pd.DataFrame,
        weights: Dict[str, float] | None = None,
        initial_capital: float = 100000.0,
    ) -> pd.Series:
        """Blend equity curves using explicit constituent weights."""
        if equity_curves_df.empty:
            return pd.Series(dtype=float)
        if weights is None:
            weights = {column: 1.0 / len(equity_curves_df.columns) for column in equity_curves_df.columns}

        weighted_pnl = []
        for column in equity_curves_df.columns:
            weight = weights.get(column, 0.0)
            pnl = (equity_curves_df[column] - initial_capital) * weight
            weighted_pnl.append(pnl)
        total_pnl = pd.concat(weighted_pnl, axis=1).sum(axis=1)
        return initial_capital + total_pnl
        
    @staticmethod
    def compute_portfolio_metrics(synthetic_equity_curve: pd.Series) -> Dict[str, float]:
        """
        Computes standard metrics on the rolled-up macro portfolio.
        """
        returns = synthetic_equity_curve.pct_change().dropna()
        
        return {
            "portfolio_sharpe": sharpe_ratio(returns),
            "portfolio_max_drawdown": max_drawdown(synthetic_equity_curve),
            "portfolio_final_value": synthetic_equity_curve.iloc[-1] if not synthetic_equity_curve.empty else 0.0
        }
