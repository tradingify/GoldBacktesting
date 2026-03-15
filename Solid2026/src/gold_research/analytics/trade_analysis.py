"""
Granular Trade Level Analytics.

Drills down into the specific mechanics of individual executed trades,
finding profit distributions, MAE (Maximum Adverse Excursion), and
MFE (Maximum Favorable Excursion) logic.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any

class TradeAnalyzer:
    
    @staticmethod
    def compute_distributions(trades: pd.DataFrame) -> Dict[str, float]:
        """
        Analyzes the mathematical distribution characteristics of the PnL sequence.
        """
        if trades.empty or 'pnl' not in trades.columns:
            return {}
            
        pnl = trades['pnl']
        winners = pnl[pnl > 0]
        losers = pnl[pnl <= 0]
        
        return {
            "avg_win": winners.mean() if not winners.empty else 0.0,
            "avg_loss": losers.mean() if not losers.empty else 0.0,
            "largest_win": pnl.max(),
            "largest_loss": pnl.min(),
            "skewness": pnl.skew(),
            "kurtosis": pnl.kurtosis()
        }
        
    @staticmethod
    def analyze_mae_mfe(trades: pd.DataFrame) -> Dict[str, float]:
        """
        If the engine provides `max_adverse_excursion` and `max_favorable_excursion`
        metrics per trade, this averages them to see how much heat the strategy 
        takes on average before working out.
        """
        # Note: Nautilus Trader requires specific tracking settings to produce MAE/MFE on Fill logic.
        # Assuming placeholders for the schema map.
        result = {}
        if 'mae' in trades.columns:
            result['avg_mae'] = trades['mae'].mean()
        if 'mfe' in trades.columns:
            result['avg_mfe'] = trades['mfe'].mean()
            
        return result