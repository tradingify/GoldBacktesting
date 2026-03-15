# Gold Research Factory — Project Memory

> **Purpose of this document**: This README is the full project memory. Hand it to the AI agent at the start of any new session to restore full context of the project: its architecture, rules, codebase map, sprint history, and next steps.

> **Current platform state (2026-03-14)**: The project now has a canonical SQLite-backed research pipeline for single runs, grid/random search, walk-forward validation, stress testing, promotion tracking, and portfolio assembly. Eligible successful single-run candidates now trigger automatic walk-forward and stress validation as part of the standard promotion flow. Older JSON ledgers remain on disk for historical compatibility, but the active execution path is now the SQLite-backed canonical pipeline.

> **Strategy intake handoff**: New ideas should be introduced using `D:\.openclaw\GoldBacktesting\Solid2026\docs\STRATEGY_INTAKE_TEMPLATE.md` so any human or AI agent can translate them into the mandatory research lifecycle consistently.

---

## 0. Executive Mandate

This project builds a **professional, falsification-first quantitative research factory for systematic gold trading** using **Nautilus Trader** as the execution engine.

This is **not** a single-strategy project.  
This is **not** an indicator optimization project.  
This is **not** a curve-fitting exercise.

### Core Goal
Build a robust, reproducible, modular research and backtesting platform that can:
1. Ingest and validate gold market data from IBKR (Interactive Brokers)
2. Generate large families of systematic strategies
3. Backtest them consistently using Nautilus Trader
4. Evaluate under realistic execution assumptions
5. Falsify fragile ideas aggressively
6. Retain only robust, multi-dimensional survivors
7. Combine surviving candidates into a diversified portfolio
8. Preserve all metadata, experiments, assumptions, and decisions

**The target outcome**: A professional research pipeline capable of discovering and ranking profitable, robust, and diversifying strategy candidates on gold across multiple timeframes and regimes.

---

## 1. Primary Research Principles (Non-Negotiable)

### 1.1 Reproducibility First
Every experiment must be reproducible from config, code version, data version, and execution assumptions.

### 1.2 Separation of Concerns
Data engineering → Feature engineering → Strategy logic → Execution assumptions → Risk sizing → Orchestration → Evaluation → Portfolio construction — each is a separate layer.

### 1.3 Falsification Over Confirmation
The goal is **not** to prove a strategy works.  
The goal is to **try to kill it**.  
Only survivors advance.

### 1.4 Modular Strategy Design
Every strategy = Regime Filter + Signal Logic + Entry Logic + Exit Logic + Position Sizing + Execution Model.

### 1.5 Parameter Stability Over Parameter Peaks
Do not find the single best parameter set. Find **stable parameter regions**.

### 1.6 Portfolio Thinking From Day One
A strong portfolio of average-but-diversifying systems is superior to one fragile "best" system.

### 1.7 Professional Research Hygiene
All runs must be logged. All results stored. All assumptions explicit. All promotions and rejections documented.

### 1.8 Master Operating Flow (Mandatory)
Any agent or human using this research factory should follow this operating chain:

1. Research Framing
2. Hypothesis Formation
3. Strategy Specification
4. Data Ingestion
5. Data Normalization
6. Data Validation
7. Dataset Registration
8. Feature Engineering
9. Strategy Assembly
10. Experiment Definition
11. Baseline Backtesting
12. Result Logging
13. Performance Evaluation
14. Candidate Screening
15. Parameter Stability Testing
16. Walk-Forward Validation
17. Out-of-Sample Validation
18. Cost Stress Testing
19. Start-Date Sensitivity Testing
20. Regime Segmentation
21. Falsification
22. Robustness Assessment
23. Promotion Decision
24. Candidate Clustering
25. Redundancy Elimination
26. Portfolio Fit Analysis
27. Risk Budgeting
28. Portfolio Construction
29. Portfolio Backtesting
30. Portfolio Evaluation
31. Portfolio Robustness Testing
32. Model Promotion
33. Research Documentation
34. Research Governance
35. Iteration Planning

### 1.9 Compressed Professional Lifecycle
For shorthand, the full process compresses to:

**Research Framing → Hypothesis Formation → Strategy Specification → Data Ingestion → Data Validation → Dataset Registration → Feature Engineering → Strategy Assembly → Experiment Definition → Baseline Backtesting → Performance Evaluation → Candidate Screening → Parameter Stability Testing → Walk-Forward Validation → Out-of-Sample Validation → Cost Stress Testing → Start-Date Sensitivity Testing → Regime Segmentation → Falsification → Robustness Assessment → Promotion Decision → Candidate Clustering → Redundancy Elimination → Portfolio Fit Analysis → Risk Budgeting → Portfolio Construction → Portfolio Backtesting → Portfolio Evaluation → Portfolio Robustness Testing → Model Promotion → Research Documentation → Research Governance → Iteration Planning**

### 1.10 Eight Formal Phases
#### Phase 1 — Research Design
- Research Framing
- Hypothesis Formation
- Strategy Specification

#### Phase 2 — Data Readiness
- Data Ingestion
- Data Normalization
- Data Validation
- Dataset Registration

#### Phase 3 — Model Construction
- Feature Engineering
- Strategy Assembly
- Experiment Definition

#### Phase 4 — Discovery
- Baseline Backtesting
- Result Logging
- Performance Evaluation
- Candidate Screening

#### Phase 5 — Validation
- Parameter Stability Testing
- Walk-Forward Validation
- Out-of-Sample Validation
- Cost Stress Testing
- Start-Date Sensitivity Testing
- Regime Segmentation

#### Phase 6 — Falsification and Robustness
- Falsification
- Robustness Assessment
- Promotion Decision

#### Phase 7 — Portfolio Integration
- Candidate Clustering
- Redundancy Elimination
- Portfolio Fit Analysis
- Risk Budgeting
- Portfolio Construction
- Portfolio Backtesting
- Portfolio Evaluation
- Portfolio Robustness Testing

#### Phase 8 — Governance and Continuation
- Model Promotion
- Research Documentation
- Research Governance
- Iteration Planning

### 1.11 Core Checkpoint Memory
If you only remember the most important checkpoints, remember this chain:

**Discovery → Screening → Validation → Falsification → Robustness Assessment → Promotion Decision → Clustering → Portfolio Fit Analysis → Portfolio Construction → Portfolio Robustness Testing → Model Promotion**

### 1.12 Must-Follow Research Operating Model
This is the mandatory operating model for any future strategy intake, whether the work is done by:
- the project owner
- Codex
- ChatGPT
- Gemini
- any future AI agent

No strategy should bypass this sequence.

#### A-to-Z Intake Flow
1. **Add Strategy Code**  
   Implement the strategy in the canonical strategy package with reusable config fields and no one-off execution path.
2. **Define Hypothesis**  
   State what market behavior the strategy is trying to exploit and why it might work on gold.
3. **Choose Dataset and Timeframe**  
   Select the exact registered dataset(s) and timeframe(s) to test.
4. **Ingest and Normalize Data**  
   Bring raw bars into the processed area.
5. **Validate Data Quality**  
   Run quality checks before any real research begins.
6. **Register Dataset**  
   Persist the dataset manifest and checksum trail.
7. **Create Experiment Spec**  
   Encode the strategy, parameters, dataset, risk profile, and cost profile in YAML.
8. **Run Discovery Search**  
   Use `run-single`, `run-grid`, or `run-random-search` to explore the hypothesis space.
9. **Persist Canonical Artifacts**  
   Every run must write scorecards, manifests, metrics, and raw execution artifacts.
10. **Apply Screening Gate**  
    Reject weak runs early using trade count, Sharpe, profit factor, and drawdown sanity.
11. **Assign Initial Promotion State**  
    The system must mark each run as `candidate_for_robustness`, `hold_for_review`, or `rejected`.
12. **Trigger Automatic Validation for Survivors**  
    Any eligible successful single-run survivor must automatically receive walk-forward and stress validation.
13. **Run Walk-Forward Validation**  
    Use rolling IS/OOS windows and local parameter neighborhoods to test forward stability.
14. **Run Stress Validation**  
    Re-run the same strategy under optimistic, base, and harsh friction assumptions.
15. **Apply Validation Gate**  
    Promote only if walk-forward efficiency and harsh-friction retention clear the thresholds.
16. **Record Final Strategy State**  
    Persist validation decisions and updated promotion states in SQLite.
17. **Generate Human-Readable Reports**  
    Produce strategy cards and sprint summaries for review.
18. **Build Candidate Pool**  
    Only non-rejected promoted strategies enter portfolio consideration.
19. **Cluster and De-Redundify**  
    Reduce overlap by family, timeframe, and behavior before portfolio assembly.
20. **Construct Portfolios**  
    Assemble multiple portfolio templates from validated survivors.
21. **Run Portfolio Robustness Checks**  
    Use leave-one-out, weight perturbation, and correlation diagnostics.
22. **Promote Portfolios, Not Just Strategies**  
    Treat portfolio readiness as the final practical milestone before paper or live trading.
23. **Document Decisions**  
    All promotions, rejections, assumptions, and unusual overrides must be recorded.
24. **Iterate**  
    Expand, refine, or kill strategy families based on stored evidence.

#### Enforcement Rules
- No strategy may move from discovery to portfolio candidacy without screening.
- No strategy may move from screening survivor to portfolio candidacy without walk-forward and stress validation.
- No rejected strategy may enter a portfolio candidate pool.
- Grid/random search children are discovery evidence, not automatically portfolio-ready models.
- Automatic validation is reserved for eligible survivor runs so the system scales without validating every permutation.
- Manual overrides are allowed only if documented with a clear reason.

#### Standard Intake Policy for New Strategy Families
When a new batch of strategies is introduced (for example 20 new strategies), the default policy is:
1. register or confirm the datasets first
2. create one canonical experiment spec per strategy
3. run discovery on each strategy family
4. let screening eliminate weak candidates
5. let the system automatically run walk-forward and stress on survivors
6. promote only validated survivors into the portfolio candidate pool
7. build multiple portfolios from the survivor pool

This policy should be treated as a standing operating rule for the repository, not a one-time sprint instruction.

### 1.13 Strategy Intake Document
All new indicators, strategies, models, and candidates should be handed off using:

`D:\.openclaw\GoldBacktesting\Solid2026\docs\STRATEGY_INTAKE_TEMPLATE.md`

This document defines:
- what the human should provide
- what the AI should do next
- the minimum required strategy handoff structure
- the mandatory instruction that tells any AI to follow the README lifecycle

If a new AI model is introduced to the project, this document should be given alongside `README.md`.

---

## 2. Environment Setup

| Property | Value |
|---|---|
| **Project Root** | `D:\.openclaw\GoldBacktesting\Solid2026\` |
| **Python path (PYTHONPATH)** | `D:\.openclaw\GoldBacktesting\Solid2026` |
| **IBKR Bar data source** | `D:\.openclaw\GoldBacktesting\bars\` |
| **Nautilus DataCatalog** | `D:\.openclaw\GoldBacktesting\Solid2026\data\catalog\` |
| **Results** | `D:\.openclaw\GoldBacktesting\Solid2026\results\` |
| **Canonical research DB** | `D:\.openclaw\GoldBacktesting\Solid2026\data\manifests\research.db` |
| **Scratch scripts** | `C:\Users\wahdatw\.gemini\antigravity\scratch\` |
| **Execution Engine** | Nautilus Trader (Python installed in active env) |
| **Instrument** | XAUUSD — InstrumentId format: `XAUUSD-IDEALPRO-USD` |
| **Timeframes researched** | 5m, 15m, 1h, 4h |

### How to run the CLI
```powershell
$env:PYTHONPATH="D:\.openclaw\GoldBacktesting\Solid2026"
python D:\.openclaw\GoldBacktesting\Solid2026\src\gold_research\cli\main.py <command>
```

### Available CLI Commands
| Command | Description |
|---|---|
| `ingest-data` | Load IBKR parquet data |
| `validate-data` | Run quality checks for a registered dataset |
| `register-dataset` | Register a dataset manifest |
| `run-single --experiment <yaml>` | Run a single backtest |
| `run-grid --experiment <yaml>` | Run exhaustive grid search |
| `run-walkforward --experiment <yaml>` | Walk-forward validation with IS/OOS child runs |
| `run-stress --run-id <id>` | Friction gauntlet for an existing run |
| `build-strategy-card --run-id <id>` | Generate strategy tearsheet |
| `build-sprint-report` | Generate sprint summary markdown |
| `build-html-dashboard` | Generate the human-facing HTML dashboard for runs and portfolios |

### Canonical Storage Model
- **Single source of truth** for run, gate, queue, promotion, and portfolio state: `data/manifests/research.db`
- **Canonical run artifacts** live under `results/raw_runs/<experiment_id>/<run_id>/`
- Required run artifacts:
  - `spec.yaml`
  - `run_manifest.json`
  - `metrics.json`
  - `scorecard.json`
  - `gate_results.json`
  - `fills.csv` / `positions.csv` / `equity.csv` when available
  - `error.json` on failure
- **Dataset manifests** remain JSON files under `data/manifests/dataset_versions/`, but are also mirrored into SQLite
- **Human-facing HTML dashboard** lives under `data/manifests/reports/html/`
  - `index.html` = master table of tested/passed/failed/rejected/candidate_for_portfolio
  - `runs/<run_id>.html` = per-run report
  - `portfolios/<portfolio_id>.html` = portfolio member/weight report

### Critical Nautilus Trader API Notes (resolved issues)
- `trader_id` must be `"BACKTESTER-001"` (hyphen format for Rust validation)
- `add_venue()` requires `OmsType` and `AccountType` args
- Starting balances must use `Money.from_str("100000 USD")` format
- `CurrencyPair` requires `Currency.from_str("XAU")` for base/quote, NOT `Symbol`
- Margin/fee fields require `Decimal("0")`, NOT `Quantity.from_int(0)`
- `InstrumentId` must be manually parsed from our internal format (`XAUUSD-IDEALPRO-USD`) — do NOT use `InstrumentId.from_str()` as it breaks on the hyphenated taxonomy
- Portfolio retrieval: use `self.engine.trader.portfolios()`, NOT deprecated `portfolio_state_objects()`

---

## 3. Codebase Structure

```
Solid2026/
├── config/
│   ├── global/
│   │   ├── data.yaml           # Timezone, source, instrument map, bar definitions
│   │   ├── costs.yaml          # Commission, spread, slippage; 3 profiles: optimistic/base/harsh
│   │   ├── sessions.yaml       # Active trading session boundaries
│   │   ├── risk.yaml           # Risk per trade, max exposure, drawdown de-risking
│   │   └── evaluation.yaml     # Min trade counts, passing thresholds, promotion rules
│   ├── datasets/
│   │   ├── starter.yaml
│   │   └── gold_primary.yaml
│   └── experiments/
│       ├── sprint_00/sample.yaml
│       └── sprint_01/macross.yaml
│
├── data/
│   ├── raw/ib/gold/bars/       # Legacy local copy path (do not treat as canonical source)
│   ├── processed/gold/bars/    # Normalized bars
│   ├── catalog/                # Nautilus ParquetDataCatalog (auto-managed)
│   ├── checks/quality_reports/ # Data validation reports
│   └── manifests/
│       ├── dataset_versions/   # Dataset manifests
│       ├── research.db         # Canonical SQLite store for runs, queues, gates, promotions, portfolios
│       ├── experiment_log.json # Legacy compatibility ledger
│       ├── promotion_log.json  # Legacy compatibility ledger
│       └── reports/
│           ├── strategies/     # Strategy tearsheets (<run_id>_card.md)
│           ├── portfolios/     # Portfolio macro cards
│           └── sprints/        # Sprint markdown reports
│
├── results/
│   ├── raw_runs/               # Per-run: spec.yaml, scorecard.json
│   └── robustness/sprint_02/  # Per-strategy robustness.json
│
└── src/gold_research/
    ├── core/
    │   ├── paths.py            # ProjectPaths: all canonical paths
    │   ├── logging.py          # Standardized logging
    │   ├── ids.py              # Deterministic run/experiment ID generation
    │   ├── config.py           # load_yaml / save_yaml helpers
    │   ├── enums.py            # StrategyFamily, Timeframe, etc.
    │   └── dataclasses.py      # Shared pydantic models
    │
    ├── data/
    │   ├── ingest/
    │   │   ├── ib_loader.py    # Loads IBKR parquet bars, handles timezones
    │   │   ├── normalize.py    # Schema normalization
    │   │   └── bar_builder.py  # Converts DataFrame → Nautilus Bar objects
    │   ├── validation/
    │   │   ├── schema_checks.py
    │   │   ├── time_checks.py
    │   │   ├── price_checks.py
    │   │   └── quality_report.py
    │   └── datasets/
    │       ├── registry.py
    │       └── manifest.py
    │
    ├── execution/
    │   ├── cost_model.py       # Loads cost profiles from costs.yaml
    │   ├── slippage_model.py   # ATR-based slippage
    │   └── fill_model.py       # Fill simulation hooks
    │
    ├── risk/
    │   ├── position_sizing.py  # Fixed risk per trade (ATR-based)
    │   ├── risk_budget.py      # Portfolio-level risk gating
    │   └── exposure_limits.py  # Max concurrent exposure helpers
    │
    ├── strategies/
    │   ├── base/
    │   │   ├── strategy_base.py  # GoldStrategy(Strategy) + GoldStrategyConfig(StrategyConfig)
    │   │   ├── signal_base.py    # SignalBase protocol + SignalIntent dataclass
    │   │   ├── exit_base.py      # ExitBase protocol
    │   │   └── filter_base.py    # RegimeFilter protocol
    │   ├── common/
    │   │   ├── indicators.py     # DonchianChannel, BollingerBands, TrueRange, ZScore, VWAP
    │   │   ├── entries.py        # MarketEntryExecutor
    │   │   ├── exits.py          # TrailATRStopExit, FixedBarExit
    │   │   ├── sizing.py         # DynamicRiskSizer
    │   │   └── helpers.py        # Utility functions
    │   ├── trend/
    │   │   ├── donchian_breakout.py    # DonchianBreakout + DonchianBreakoutConfig
    │   │   ├── moving_average_cross.py # MovingAverageCross + MACrossConfig
    │   │   └── atr_breakout.py         # ATRBreakout + ATRBreakoutConfig
    │   ├── mean_reversion/
    │   │   ├── bollinger_reversion.py  # BollingerReversion + BollingerReversionConfig
    │   │   ├── zscore_reversion.py     # ZScoreReversion + ZScoreReversionConfig
    │   │   └── vwap_reversion.py       # VwapReversion + VWAPReversionConfig
    │   ├── breakout/
    │   │   ├── opening_range_breakout.py # OpeningRangeBreakout + ORBConfig
    │   │   └── squeeze_breakout.py       # SqueezeBreakout + SqueezeBreakoutConfig
    │   ├── pullback/
    │   │   └── ema_pullback.py          # EmaPullback + EMAPullbackConfig
    │   └── hybrid/
    │       └── regime_switching_breakout_reversion.py # RegimeHybrid + HybridRegimeConfig
    │
    ├── backtests/
    │   ├── engine/
    │   │   ├── adapters.py        # Nautilus boilerplate: venue, instrument, data loading
    │   │   └── nautilus_runner.py # NautilusRunner: wraps BacktestEngine end-to-end
    │   ├── orchestration/
    │   │   ├── run_single.py      # run_single(spec) → persists spec.yaml + scorecard.json
    │   │   ├── run_grid.py        # run_grid(base_spec, param_grid)
    │   │   ├── run_random_search.py
    │   │   ├── run_walkforward.py # generate_wfo_windows() + rolling IS/OOS
    │   │   └── run_stress_suite.py # optimistic/base/harsh friction profiles
    │   └── specifications/
    │       ├── experiment_spec.py  # ExperimentSpec(BaseModel) + DatasetSpec
    │       └── parameter_grid.py   # ParameterGrid(params_dict).generate_grid()
    │
    ├── analytics/
    │   ├── metrics.py       # sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio
    │   ├── scorecards.py    # StrategyScorecard(BaseModel) + generate_scorecard()
    │   ├── robustness.py    # RobustnessAnalyzer: WFE + stress/stroll summaries
    │   ├── sensitivity.py   # Parameter sensitivity hooks
    │   ├── regimes.py       # Regime classification utilities
    │   ├── equity.py        # Equity curve analytics
    │   ├── trade_analysis.py
    │   ├── clustering.py    # ClusteringAnalyzer: correlation matrix + high-corr pairs
    │   └── portfolio.py     # PortfolioComposer: weighted equity + portfolio metrics
    │
    ├── gates/
    │   ├── screening.py     # Discovery-stage gate: candidate_for_robustness / hold / reject
    │   └── validation.py    # WFO/stress gate: candidate_for_portfolio / hold / reject
    │
    ├── pipeline/
    │   ├── run_pipeline.py  # Canonical run execution and artifact persistence
    │   ├── bar_processor.py
    │   └── event_registry.py
    │
    ├── store/
    │   ├── db.py            # SQLite initialization and lightweight migrations
    │   ├── schema.py        # Canonical schema
    │   ├── runs_repo.py     # Run lifecycle + artifacts
    │   ├── queue_repo.py    # Batch queue persistence
    │   ├── promotions_repo.py
    │   ├── datasets_repo.py
    │   └── portfolio_repo.py
    │
    ├── portfolio/
    │   ├── selector.py      # Promoted-run selection from SQLite
    │   ├── allocator.py     # Equal weight / inverse-vol / Sharpe tilt / family cap
    │   ├── templates.py     # Portfolio templates
    │   ├── robustness.py    # Leave-one-out and weight perturbation diagnostics
    │   └── pipeline.py      # Canonical portfolio assembly pipeline
    │
    ├── registry/
    │   ├── experiment_registry.py  # Legacy compatibility ledger
    │   ├── strategy_registry.py
    │   └── promotion_registry.py   # Legacy compatibility ledger
    ├── reports/
    │   ├── strategy_card.py   # StrategyCardReport.generate_markdown() + save_report()
    │   ├── portfolio_card.py  # PortfolioCardReport.generate_markdown() + save_report()
    │   └── sprint_report.py   # SprintReport.build_sprint_summary() + save_report()
    │
    └── cli/
        └── main.py            # argparse CLI with all major commands wired
```

---

## 4. Instrument ID Convention

Internal format: `XAUUSD-IDEALPRO-USD`
- Symbol: `XAUUSD`
- Venue: `IDEALPRO` (Interactive Brokers)
- Quote currency: `USD`

When creating Nautilus objects, manually parse this:
```python
parts = instrument_id_str.split("-")
symbol = parts[0]    # "XAUUSD"
venue  = parts[1]    # "IDEALPRO"
```

---

## 5. Data Flow (Current Status)

### Real IBKR Data
- Raw parquet files are sourced from `D:\.openclaw\GoldBacktesting\bars\`
- `ingest-data --instrument gold` normalizes source parquet into `data/processed/gold/bars/`
- Loaded via `src/gold_research/data/ingest/ib_loader.py` (`load_ib_parquet()`)
- Normalized and converted to Nautilus `Bar` objects via `bar_builder.py` (`df_to_nautilus_bars()`)
- Registered via `register-dataset`, which writes both a JSON manifest and a SQLite dataset record
- Canonical execution will use the Nautilus catalog when present, or fall back to registered parquet source files

### Mock Data (Sprint 00–03 testing only)
- Used `C:\Users\wahdatw\.gemini\antigravity\scratch\mock_data.py` to generate synthetic OHLC data
- Generated for 5m, 15m, 1h, 4h timeframes covering 2023 full year
- **For Sprint 04+ we switch to real IBKR data from the `/bars` folder**

---

## 6. Strategy Promotion Lifecycle

```
New Strategy / Experiment Spec
    ↓
Discovery Run (canonical single-run pipeline)
  → Writes artifacts + scorecard + screening gate result
  → States:
      rejected / hold_for_review / candidate_for_robustness
    ↓
Validation Family
  → Walk-forward child runs
  → Stress child runs
  → Validation gate result
  → States:
      rejected / hold_for_review / candidate_for_portfolio
    ↓
Portfolio Factory
  → Candidate selection from SQLite promotion state
  → Family-aware allocation template
  → Portfolio robustness diagnostics
  → Portfolio persistence + macro report
```

---

## 7. Sprint History

### Sprint 00: Infrastructure and Truthfulness ✅ COMPLETE
**Objective**: Verify the project runs end-to-end on synthetic data.

**Blockers Fixed**:
- Nautilus Rust `trader_id` format validation
- `add_venue()` now requires `OmsType` + `AccountType`
- `Money.from_str("100000 USD")` for starting balances
- `Currency.from_str("XAU")` for `CurrencyPair` base/quote currencies
- Margin/fee fields must use `Decimal("0")`
- Custom `InstrumentId` parsing (bypasses native `.from_str()`)
- Portfolio extraction uses `engine.trader.portfolios()`

**Outputs**:
- `results/raw_runs/SPRINT_00_BASELINE/run_68eb4f3f/spec.yaml`
- `results/raw_runs/SPRINT_00_BASELINE/run_68eb4f3f/scorecard.json`
- `data/manifests/reports/strategies/run_68eb4f3f_card.md`

---

### Sprint 01: Baseline Strategy Discovery ✅ COMPLETE
**Objective**: Broad coarse-grid scan of all 10 strategy templates on 5m, 15m, 1h, 4h.

**Results**:
- 76 combinations evaluated
- 43 (56%) rejected: Sharpe < 0.5 or PF < 1.0
- **33 survivors** → `data/manifests/reports/sprint_01_survivors.json`

**Top 5 Pre-Friction**:
1. EMAPullback / 15m — Sharpe 2.43, PF 1.89
2. SqueezeBreakout / 1h — Sharpe 2.43, PF 1.05
3. VwapReversion / 15m — Sharpe 2.28, PF 1.14
4. VwapReversion / 5m — Sharpe 2.27, PF 1.02
5. BollReversion / 15m — Sharpe 2.15, PF 2.25

---

### Sprint 02: Robustness & Falsification ✅ COMPLETE
**Objective**: Attempt to kill all 33 Sprint 01 survivors through 5 adversarial dimensions.

**Results**:
- 23 strategies **REJECTED**
  - Walk-forward collapse: 12 strategies (OOS Sharpe didn't hold)
  - Cost stress failure: 11 strategies (harsh PF < 1.0)
- **10 strategies promoted** → `CANDIDATE_FOR_PORTFOLIO`

| Rank | Strategy | TF | Robustness Score | Sharpe |
|---|---|---|---|---|
| 1 | Donchian | 5m | 87.3 | 2.13 |
| 2 | SqueezeBreakout | 5m | 85.2 | 0.67 |
| 3 | Donchian | 1h | 81.8 | 1.84 |
| 4 | BollReversion | 15m | 81.7 | 2.15 |
| 5 | SqueezeBreakout | 15m | 81.3 | 1.95 |
| 6 | SqueezeBreakout | 4h | 78.5 | 1.16 |
| 7 | EMAPullback | 4h | 78.3 | 1.23 |
| 8 | Donchian | 4h | 77.2 | 1.36 |
| 9 | BollReversion | 5m | 76.0 | 1.51 |
| 10 | ZScoreReversion | 15m | 74.5 | 1.79 |

**Stored per-strategy**: `results/robustness/sprint_02/<strategy>/<tf>/robustness.json`

---

### Sprint 03: Portfolio Assembly ✅ COMPLETE
**Objective**: Build the first diversified gold strategy portfolio.

**Method**:
- Pearson correlation clustering (ρ > 0.70 threshold): **No pairs found — all 10 naturally decorrelated**
- Inverse-volatility weighting on 252-day simulated returns

**Selected Portfolio — GOLD_PORT_01**:

| Strategy | Timeframe | Weight | Sharpe |
|---|---|---|---|
| BollReversion | 15m | 16.0% | 2.15 |
| Donchian | 1h | 14.4% | 1.84 |
| SqueezeBreakout | 5m | 13.3% | 0.67 |
| EMAPullback | 4h | 8.9% | 1.23 |
| ZScoreReversion | 15m | 8.5% | 1.79 |
| Donchian | 5m | 8.2% | 2.13 |
| SqueezeBreakout | 15m | 8.0% | 1.95 |
| BollReversion | 5m | 7.8% | 1.51 |
| Donchian | 4h | 7.5% | 1.36 |
| SqueezeBreakout | 4h | 7.3% | 1.16 |

**Portfolio Metrics** (synthetic simulation, 252-day Monte Carlo):
| Metric | Value |
|---|---|
| Blended Sharpe | 6.77 |
| Max Drawdown | -2.37% |
| Net PnL | $66,073 |
| Final Value | $166,073 |

> Note: Blended Sharpe is elevated due to low-correlation simulation. Real-world figures will be compressed by execution costs and true regime correlations.

**Outputs**:
- `data/manifests/reports/sprint_03_portfolio.json`
- `data/manifests/reports/portfolios/GOLD_PORT_01_macro.md`
- `data/manifests/reports/sprints/sprint_03_report.md`

### Sprint 04: Real Data Validation ✅ COMPLETE
**Objective**: Validate all 10 GOLD_PORT_01 strategies against real IBKR bar data.

**Method**: Bypassed Nautilus `DataCatalog` for direct parquet loading via `ib_loader.py` → `bar_builder.py` → `BacktestEngine`. Runner script: `scripts/run_sprint04.py`.

**Pipeline Bugs Fixed** (9 total): bar subscription, price precision, negative volume, portfolio API, instrument ID, sizer args, contract multiplier, PnL string format, exit position passing.

**Results** — 10/10 executed, **3 PASS, 7 FAIL**:

| Strategy | TF | Synth Sharpe | Real Sharpe | Real PF | Trades | Net P&L | Verdict |
|---|---|---|---|---|---|---|---|
| **BollReversion** | **15m** | 2.15 | **6.74** | **4.80** | 1,064 | +$11,959 | ✅ PASS |
| **ZScoreReversion** | **15m** | 1.79 | **5.03** | **4.56** | 1,512 | +$11,689 | ✅ PASS |
| **SqueezeBreakout** | **5m** | 0.67 | **0.55** | **1.15** | 1,705 | +$793 | ✅ PASS |
| Donchian | 5m/1h/4h | 2.13/1.84/1.36 | 0.00 | 0.00 | 0 | $0 | ❌ FAIL |
| SqueezeBreakout | 15m | 1.95 | -10.22 | 0.07 | 816 | -$14,815 | ❌ FAIL |
| SqueezeBreakout | 4h | 1.16 | -1.96 | 0.69 | 101 | -$693 | ❌ FAIL |
| EMAPullback | 4h | 1.23 | -0.87 | 0.82 | 306 | -$777 | ❌ FAIL |
| BollReversion | 5m | 1.51 | -0.44 | 0.91 | 3,425 | -$910 | ❌ FAIL |

**Key Findings**:
- Mean-reversion at 15m performs *better* on real data than synthetic
- All 3 Donchian variants produce 0 trades (signal generator issue)
- SqueezeBreakout 15m catastrophically overfitted (Sharpe 1.95→-10.22)

**Outputs**:
- `results/raw_runs/SPRINT_04_REAL/sprint_04_report.html` ← visual dashboard
- `results/sprint_04_tracker.json`
- Per-strategy: `results/raw_runs/SPRINT_04_REAL/<run_id>/` (scorecard, fills, positions CSVs)
---

### Sprint 05: Real Data Portfolio Assembly ✅ COMPLETE
**Objective**: Build GOLD_PORT_02 from the 3 real-data-validated strategies.

**Method**: Extract daily PnL from positions CSVs → pairwise Pearson correlations → inverse-volatility weighting → simulate blended portfolio. Runner: `scripts/run_sprint05.py`.

**Donchian Bug Fix**: Fixed `DonchianChannel` indicator (current bar was included in upper/lower, making breakout signals impossible). After fix: Donchian produces trades (2505/409/92) but still fails validation (negative Sharpe).

**GOLD_PORT_02 Composition**:

| Strategy | TF | Weight | Sharpe | Net PnL | Win Rate |
|---|---|---|---|---|---|
| SqueezeBreakout | 5m | 50.8% | 1.29 | +$804 | 44% |
| BollReversion | 15m | 27.8% | 10.31 | +$11,947 | 82% |
| ZScoreReversion | 15m | 21.5% | 7.82 | +$11,679 | 75% |

**Correlations** (daily returns):
- BollReversion vs ZScoreReversion: ρ = 0.60 (moderate)
- BollReversion vs SqueezeBreakout: ρ = -0.01 (uncorrelated ✅)
- ZScoreReversion vs SqueezeBreakout: ρ = 0.21 (low ✅)

**Portfolio Metrics — GOLD_PORT_02**:
| Metric | Value |
|---|---|
| Sharpe | 8.88 |
| Sortino | 55.09 |
| Profit Factor | 15.54 |
| Max Drawdown | -0.04% |
| Calmar | 120.03 |
| Net PnL | $6,226 |
| Win Rate (Daily) | 76.8% |

**Outputs**:
- `results/raw_runs/SPRINT_05_PORTFOLIO/sprint_05_report.html` ← visual dashboard with charts
- `results/raw_runs/SPRINT_05_PORTFOLIO/GOLD_PORT_02_card.json`
- `results/raw_runs/SPRINT_05_PORTFOLIO/equity_curves.csv`
- `results/raw_runs/SPRINT_05_PORTFOLIO/correlation_matrix.csv`

---

## 8. Current Status & What Comes Next

### Platform Upgrade Complete: Canonical Pipeline + Validation + Portfolio Factory ✅
The system now supports:
- Canonical single-run execution with SQLite-backed lineage
- Dataset registration and validation
- Screening gate persistence
- Batch grid/random execution with queue + dedupe fingerprints
- Walk-forward and stress child-run execution
- Portfolio construction from promoted candidates

### Next Phase: Sprint 06+

**Immediate priorities**:
1. Parameter sensitivity analysis on validated candidates
2. Regime segmentation and start-date sensitivity as first-class gates
3. Richer portfolio templates and portfolio-level stress tests
4. Live paper-trading preparation

---

## 9. Key Engineering Rules (Always Follow)

1. **Never hardcode research values** inside strategy logic — all params go in config.
2. **Every run gets a unique run_id** — use `src.gold_research.core.ids` for generation.
3. **Every scorecard must be saved** as JSON before generating the markdown card.
4. **For Nautilus types**: use `Money.from_str()`, `Currency.from_str()`, `Decimal("0")` — never raw integers or `Symbol` objects.
5. **InstrumentId**: always manually parse our `XAUUSD-IDEALPRO-USD` format — do NOT use `InstrumentId.from_str()`.
6. **All outputs go through the ProjectPaths system** — never hardcode filesystem paths in strategy logic.
7. **Promotion states** must be updated in `PromotionRegistry` for every run that completes evaluation.
8. **Strategy cards** must be generated for every promoted candidate.
9. **Lint errors from Pyre2** about missing search roots are false positives — the code runs correctly with `PYTHONPATH` set.
10. **Nested f-strings** with dict lookups cause syntax errors in some Python versions — always extract the key into a variable first.
11. **Sprint HTML Reports are mandatory**: After every completed sprint, generate a visual HTML report in `results/raw_runs/SPRINT_XX_<NAME>/sprint_XX_report.html`. The report must include: hero header, KPI strip, full strategy comparison table, deep-dive cards for passing strategies (with trade logs), failing strategy summaries, and key insights. Use `scripts/gen_sprint_report.py` as the generator template.

---

## 10. Key Files to Read First in Any New Session

| Priority | File | Why |
|---|---|---|
| 1 | `README.md` (this file) | Full project memory |
| 2 | `plan.md` | Full original specification (1138 lines) |
| 3 | `src/gold_research/core/paths.py` | All canonical paths |
| 4 | `src/gold_research/backtests/engine/adapters.py` | Nautilus API integration |
| 5 | `src/gold_research/backtests/engine/nautilus_runner.py` | Backtest execution |
| 6 | `src/gold_research/cli/main.py` | All CLI entry points |
| 7 | `data/manifests/reports/sprint_02_outcomes.json` | Sprint 02 full results |
| 8 | `data/manifests/reports/sprint_03_portfolio.json` | Current portfolio |
| 9 | `results/raw_runs/SPRINT_04_REAL/sprint_04_report.html` | Sprint 04 visual report |
| 10 | `results/sprint_04_tracker.json` | Sprint 04 strategy tracker |
