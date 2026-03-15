"""
Core Analytics Metrics.

Calculates foundational quantitative metrics from a stream of portfolio
equity returns or trade logs.
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Any

def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """Calculates annualized Sharpe Ratio."""
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    excess_returns = returns - (risk_free_rate / periods_per_year)
    return np.sqrt(periods_per_year) * (excess_returns.mean() / excess_returns.std())

def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """Calculates annualized Sortino Ratio (downside deviation)."""
    if len(returns) < 2:
        return 0.0
    excess_returns = returns - (risk_free_rate / periods_per_year)
    downside_returns = excess_returns[excess_returns < 0]
    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return np.inf if excess_returns.mean() > 0 else 0.0
    return np.sqrt(periods_per_year) * (excess_returns.mean() / np.sqrt(np.mean(downside_returns**2)))

def calculate_drawdowns(equity_curve: pd.Series) -> pd.Series:
    """Calculates running drawdown percentage from high water mark."""
    rolling_max = equity_curve.cummax()
    drawdowns = (equity_curve - rolling_max) / rolling_max
    return drawdowns

def max_drawdown(equity_curve: pd.Series) -> float:
    """Calculates maximum absolute percentage drawdown."""
    dd = calculate_drawdowns(equity_curve)
    if dd.empty:
        return 0.0
    return float(dd.min())

def calmar_ratio(returns: pd.Series, equity_curve: pd.Series, periods_per_year: int = 252) -> float:
    """Annualized Return / Max Drawdown."""
    mdd = abs(max_drawdown(equity_curve))
    if mdd == 0:
        return 0.0
    ann_return = returns.mean() * periods_per_year
    return ann_return / mdd

def trade_expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Mathematical expectancy of a single trade (in dollars or R-multiples)."""
    loss_rate = 1.0 - win_rate
    return (win_rate * avg_win) - (loss_rate * abs(avg_loss))
