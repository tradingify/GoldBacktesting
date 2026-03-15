"""Portfolio templates built from promoted candidate runs."""

from __future__ import annotations


PORTFOLIO_TEMPLATES = {
    "mixed_all_weather": {
        "families": None,
        "allocator": "family_capped",
        "description": "Blend promoted runs across all available strategy families.",
    },
    "trend_core": {
        "families": {"trend", "breakout", "pullback"},
        "allocator": "inverse_volatility",
        "description": "Trend-leaning portfolio emphasizing breakout and continuation systems.",
    },
    "mean_reversion_core": {
        "families": {"mean_reversion"},
        "allocator": "sharpe_tilt",
        "description": "Mean reversion systems ranked by risk-adjusted edge.",
    },
}

