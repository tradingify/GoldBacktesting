Here is a new strategy intake. Implement it and run it through the mandatory A-Z lifecycle in README.md. Use the standard experiment template, canonical pipeline, automatic validation, and HTML reporting.

Use this strategy as a full intake into the Gold Research Factory.
Follow README.md as mandatory operating procedure.
Do not bypass the canonical pipeline.
Create/update code, create the experiment spec from the template, run discovery, apply screening, run automatic validation if eligible, update reports, and tell me the final promotion state.

New strategy intake:

Name: Momentum Exhaustion Reversal
Type: Mean reversion
Hypothesis: After extreme short-term momentum spikes in XAUUSD, price mean-reverts within 3-8 bars.

Indicator:
- Base indicator: custom exhaustion score
- Inputs: close, ATR(14), RSI(7)
- Logic:
  - compute z-score of 5-bar return
  - combine with RSI extreme
  - score = abs(z_return) + RSI_extreme_component
- Parameters:
  - z_threshold
  - rsi_overbought
  - rsi_oversold
  - hold_bars

Entry:
- Long when z-score < -2.0 and RSI < 20
- Short when z-score > 2.0 and RSI > 80

Exit:
- Exit after 5 bars or trailing ATR stop

Timeframe:
- Start with 15m

Dataset:
- use registered real XAUUSD 15m dataset

Goal:
- full A-Z research intake through the standard pipeline



------------
Your job
When you discover a new indicator or strategy idea, give the AI these things:

Strategy thesis
What is the idea?
What market behavior is it trying to exploit?
Why might it work on gold?
Indicator definition
Exact formula or logic
Inputs
Outputs
Any thresholds or parameters
If possible, a plain-English explanation plus pseudocode
Entry/exit rules
When to enter long/short
When to exit
Stop loss logic
Take profit / trailing logic
Any session/regime filter
Timeframe and scope
Which timeframe(s) to test first
Which dataset(s) to use
Whether this is:
trend
mean reversion
breakout
hybrid
SMC / structure
other
Search intent
Do you want:
one baseline run
a parameter sweep
a random search
a full intake into the research factory
Constraints
Risk assumptions
Cost profile if non-default
Any rule like “long only”, “NY session only”, “skip high-vol days”, etc.