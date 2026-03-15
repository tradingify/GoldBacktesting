# Strategy Intake Template

Use this template whenever you want to introduce a new indicator, strategy, model, or candidate into the Gold Research Factory.

This document is designed for:
- the project owner
- Codex
- Claude
- Openclaw
- ChatGPT
- any future AI research agent

The goal is simple:
give the AI enough structure to implement the idea correctly and then run it through the mandatory A-to-Z lifecycle defined in `README.md`.

---

## Mandatory Instruction To Include

When handing a new idea to an AI, include this instruction:

```text
Use this strategy as a full intake into the Gold Research Factory.
Follow README.md as mandatory operating procedure.
Do not bypass the canonical pipeline.
Create or update the code, create the experiment spec from the standard template, run discovery, apply screening, run automatic validation if eligible, update reports, and tell me the final promotion state.
```

---

## Copy-Paste Intake Form

```text
New strategy intake

Name:

Type:
- trend
- mean reversion
- breakout
- pullback
- hybrid
- session
- SMC / ICT
- other

Hypothesis:

Why it might work on gold:

Indicator or feature definition:
- name:
- formula / logic:
- required inputs:
- output:
- thresholds:
- notes:

Entry rules:
- long entry:
- short entry:

Exit rules:
- stop loss:
- take profit:
- trailing logic:
- time-based exit:

Filters:
- session filters:
- volatility filters:
- trend filters:
- news / event filters:
- regime filters:

Parameters to test:
- parameter_1:
- parameter_2:
- parameter_3:

Suggested parameter ranges:
- parameter_1:
- parameter_2:
- parameter_3:

Timeframe(s) to test first:

Dataset(s) to use:

Risk profile:
- base / custom

Cost profile:
- optimistic / base / harsh

Goal of this intake:
- baseline run
- random search
- grid search
- full research-factory intake

Notes or constraints:
```

---

## Minimum Required Information

At minimum, you should provide:
- a strategy name
- a hypothesis
- the indicator logic
- entry and exit logic
- the starting timeframe
- the desired test mode

If you do not provide everything, the AI should make reasonable assumptions, document them, and proceed through the standard lifecycle.

---

## What The AI Must Do After Receiving This Intake

After receiving a completed intake, the AI should:

1. interpret the idea as a formal research candidate
2. implement the indicator or feature if needed
3. implement the strategy in the correct strategy family
4. create an experiment spec from the standard template
5. run discovery through the canonical pipeline
6. let screening run automatically
7. let walk-forward and stress run automatically for eligible survivors
8. persist all artifacts and decisions
9. refresh the human-facing reports, including the HTML dashboard
10. report back with:
   - what was tested
   - what passed
   - what failed
   - what was rejected
   - final promotion state

---

## What The AI Must Not Do

The AI must not:
- bypass the experiment spec
- bypass the canonical pipeline
- manually promote a strategy without recorded evidence
- include rejected runs in a portfolio
- claim a strategy will definitely make money

---

## Recommended One-Line Prompt

If you want a short version, use this:

```text
Here is a new strategy intake. Implement it and run it through the mandatory Gold Research Factory lifecycle in README.md, including canonical execution, screening, automatic validation, reporting, and final promotion-state summary.
```

