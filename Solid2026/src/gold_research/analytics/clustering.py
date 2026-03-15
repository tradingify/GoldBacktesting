"""
Strategy Clustering and Decorrelation.

When orchestrating portfolios, it's vital to ensure 5 strategies aren't 
doing the exact same thing. This module checks correlation vectors.
"""
import pandas as pd
from typing import Dict, Any, List

class ClusteringAnalyzer:
    
    @staticmethod
    def compute_correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
        """
        Given a DataFrame where each column is the daily return stream of a specific 
        strategy `run_id`, yields the Pearson correlation matrix.
        """
        # Clean any NA misalignments if strategies started on different dates
        clean_df = returns_df.dropna()
        if clean_df.empty:
            return pd.DataFrame()
            
        return clean_df.corr(method="pearson")
        
    @staticmethod
    def find_highly_correlated_pairs(corr_matrix: pd.DataFrame, threshold: float = 0.85) -> List[tuple]:
        """
        Flags pairs of strategies that are basically identical in performance footprints.
        """
        high_corr = []
        cols = corr_matrix.columns
        
        for i in range(len(cols)):
            for j in range(i+1, len(cols)):
                 val = corr_matrix.iloc[i, j]
                 if abs(val) >= threshold:
                     high_corr.append((cols[i], cols[j], val))
                     
        return high_corr