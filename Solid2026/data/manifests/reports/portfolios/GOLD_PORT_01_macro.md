# Portfolio Tearsheet: GOLD_PORT_01
Generated on: 2026-03-09 21:14:39 UTC

## 🌍 Macro Performance (Synthetic)
- **Final Account Value**: $166,073.06
- **Blended Sharpe Ratio**: 6.77
- **Blended Max Drawdown**: -2.37%

## 🧬 Constituent Sub-Strategies (10)
- `run_Donchian_5m_4244`
- `run_SqueezeBreakout_5m_5587`
- `run_Donchian_1h_8942`
- `run_BollReversion_15m_2493`
- `run_SqueezeBreakout_15m_2908`
- `run_SqueezeBreakout_4h_3158`
- `run_EMAPullback_4h_9868`
- `run_Donchian_4h_2698`
- `run_BollReversion_5m_8427`
- `run_ZScoreReversion_15m_8360`

---
*Note: This report assumes 0 correlation penalty and execution on a shared $100k capital base.*

## ⚖️ Risk Allocation Detail

| Strategy | Weight | Robustness | Sharpe |
|---|---|---|---|
| Donchian_5m | 8.2% | 87.3 | 2.13 |
| SqueezeBreakout_5m | 13.3% | 85.2 | 0.67 |
| Donchian_1h | 14.4% | 81.8 | 1.84 |
| BollReversion_15m | 16.0% | 81.7 | 2.15 |
| SqueezeBreakout_15m | 8.0% | 81.3 | 1.95 |
| SqueezeBreakout_4h | 7.3% | 78.5 | 1.16 |
| EMAPullback_4h | 8.9% | 78.3 | 1.23 |
| Donchian_4h | 7.5% | 77.2 | 1.36 |
| BollReversion_5m | 7.8% | 76.0 | 1.51 |
| ZScoreReversion_15m | 8.5% | 74.5 | 1.79 |

## 🔬 Cluster Analysis
- Correlation threshold for redundancy pruning: **ρ > 0.70**
- Highly correlated pairs removed: **0**

## 🧮 Allocation Logic
Weights computed via **inverse-volatility** of simulated daily return streams.
Lower-volatility strategies receive proportionally more capital, dampening portfolio drawdown.

## ⚠️ Assumptions
- Return streams are Monte Carlo simulations consistent with each strategy's Sharpe and max drawdown.
- No portfolio-level transaction costs applied.
- Strategies trade on independent capital slices (no cross-margin).
