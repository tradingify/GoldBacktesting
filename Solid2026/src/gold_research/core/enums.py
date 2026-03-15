"""
Core enumerations used across the platform.

These enums standardize Timeframes, Strategy Families, Cost Profiles, 
and Execution Regimes to avoid magic strings throughout the codebase.
"""
from enum import Enum

class Timeframe(str, Enum):
    """Standardized timeframes required by the research mandate."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

class StrategyFamily(str, Enum):
    """Logical families separating strategies by archetype."""
    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    PULLBACK = "pullback"
    HYBRID = "hybrid"

class PromotionState(str, Enum):
    """States representing a strategy's status in the research funnel."""
    REJECTED = "rejected"
    HOLD_FOR_REVIEW = "hold_for_review"
    CANDIDATE_FOR_ROBUSTNESS = "candidate_for_robustness"
    CANDIDATE_FOR_PORTFOLIO = "candidate_for_portfolio"
    ARCHIVED = "archived"

class CostProfile(str, Enum):
    """Execution cost profiles for varying degrees of stress-testing."""
    OPTIMISTIC = "optimistic"
    BASE = "base"
    HARSH = "harsh"

class ExecutionRegime(str, Enum):
    """Market structure environments used for filtering trade signals."""
    NORMAL = "normal"
    HIGH_VOLATILITY = "high_vol"
    COMPRESSION = "compression"
