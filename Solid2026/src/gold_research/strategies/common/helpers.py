"""
Common Helper Diagnostics.

Assorted math and string manipulation helpers for strategy blocks.
"""

def crossover(series_fast: list, series_slow: list) -> bool:
    """
    Detects if the fast series crossed strictly above the slow series
    on the most recent tick.
    """
    if len(series_fast) < 2 or len(series_slow) < 2:
        return False
        
    curr_fast = series_fast[-1]
    curr_slow = series_slow[-1]
    prev_fast = series_fast[-2]
    prev_slow = series_slow[-2]
    
    return (prev_fast <= prev_slow) and (curr_fast > curr_slow)

def crossunder(series_fast: list, series_slow: list) -> bool:
    """
    Detects if the fast series crossed strictly below the slow series
    on the most recent tick.
    """
    if len(series_fast) < 2 or len(series_slow) < 2:
        return False
        
    curr_fast = series_fast[-1]
    curr_slow = series_slow[-1]
    prev_fast = series_fast[-2]
    prev_slow = series_slow[-2]
    
    return (prev_fast >= prev_slow) and (curr_fast < curr_slow)