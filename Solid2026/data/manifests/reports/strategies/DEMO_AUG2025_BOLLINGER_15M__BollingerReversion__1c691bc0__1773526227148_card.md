# Strategy Tearsheet: DEMO_AUG2025_BOLLINGER_15M__BollingerReversion__1c691bc0__1773526227148
Generated on: 2026-03-14 22:11:18 UTC
        
## 📈 Core Performance
- **Net Profit**: $529.64
- **Sharpe Ratio**: 12.17
- **Sortino Ratio**: 12.49
- **Max Drawdown**: -0.02%
- **Calmar Ratio**: 110.71

## ⚖️ Trade Statistics
- **Total Executions**: 66
- **Win Rate**: 80.3%
- **Profit Factor**: 7.05

## ⚙️ Hyperparameters
```json
experiment_id: DEMO_AUG2025_BOLLINGER_15M
run_id: DEMO_AUG2025_BOLLINGER_15M__BollingerReversion__1c691bc0__1773526227148
strategy_class_path: src.gold_research.strategies.mean_reversion.bollinger_reversion.BollingerReversion
strategy_params:
  timeframe: 15m
  period: 20
  std_devs: 2.0
  hold_bars: 5
dataset:
  manifest_id: xauusd_15_mins
  instrument_id: XAUUSD-IDEALPRO-USD
  start_time: '2025-08-01T00:00:00+00:00'
  end_time: '2025-08-31T23:59:59+00:00'
risk:
  profile_name: base
  starting_capital: 100000.0
costs:
  profile_name: base
author: GoldResearch
tags: []
description: ''

```

## 📝 Analyst Notes
End-to-end Sprint 00 validation.

---
*Status: COMPLETED*
