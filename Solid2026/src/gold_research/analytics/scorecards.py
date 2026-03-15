"""
Scorecard Generator.

Aggregates individual metrics into a cohesive `StrategyCard` summary.
This allows quick filtering and comparison across grid runs.
"""
from typing import Dict, Any
import pandas as pd
from pydantic import BaseModel

from src.gold_research.analytics.metrics import (
    sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio
)

class StrategyScorecard(BaseModel):
    """Normalized snapshot of a strategy's statistical footprint."""
    run_id: str
    total_trades: int
    win_rate: float
    profit_factor: float
    total_net_profit: float
    
    # Ratios
    sharpe: float
    sortino: float
    calmar: float
    max_dd_pct: float
    
    # Metadata
    status: str = "COMPLETED"

def generate_scorecard(run_id: str, equity_series: pd.Series, trades: pd.DataFrame) -> StrategyScorecard:
    """
    Transforms raw engine output series into a serialized scorecard.
    
    Args:
        run_id: Execution identifier.
        equity_series: Time series of account values.
        trades: DataFrame of executed round-trip trades.
    """
    # Defensive checks
    if trades.empty or equity_series.empty:
        return StrategyScorecard(
            run_id=run_id, total_trades=0, win_rate=0.0, profit_factor=0.0,
            total_net_profit=0.0, sharpe=0.0, sortino=0.0, calmar=0.0, max_dd_pct=0.0,
            status="EMPTY"
        )
        
    returns = equity_series.pct_change().dropna()
    
    # Trade Metrics
    winners = trades[trades['pnl'] > 0]
    losers = trades[trades['pnl'] <= 0]
    
    win_rate = len(winners) / len(trades) if len(trades) > 0 else 0.0
    gross_profit = winners['pnl'].sum() if not winners.empty else 0.0
    gross_loss = abs(losers['pnl'].sum()) if not losers.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    net_profit = gross_profit - gross_loss
    
    # Portfolio Metrics
    sharpe = sharpe_ratio(returns)
    sortino = sortino_ratio(returns)
    mdd = max_drawdown(equity_series)
    calmar = calmar_ratio(returns, equity_series)
    
    return StrategyScorecard(
        run_id=run_id,
        total_trades=len(trades),
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_net_profit=net_profit,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_dd_pct=mdd
    )