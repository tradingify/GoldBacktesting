# ICT Research Framework — Architecture Note
**Date**: 2026-03-12
**Scope**: Solid2026 Phase 1–3 foundation
**Purpose**: Document module structure, event schema, and research flow for the ICT indicator layer backing K's live gold system backtest.

---

## 1. Motivation

K's live trading system (k_scanner_v2.py + confluence_scorer.py) applies a 4-layer ICT confluence model to XAUUSD on MT5.  The goal of this framework is to:
1. Replicate the live logic in a backtestable, modular Python system.
2. Falsify individual concept hypotheses before combining them.
3. Provide a clean event-driven architecture that avoids spaghetti and lookahead bias.

---

## 2. Module Map

```
src/gold_research/
│
├── indicators/            ← ICT indicator layer (NEW — Phase 1)
│   ├── __init__.py        ← re-exports schema types
│   ├── schema.py          ← IndicatorEvent, EventType, EventState, SCORE_MATRIX
│   ├── sessions.py        ← Session windows (UTC), kill zones, Berlin offset notes
│   ├── order_blocks.py    ← OB detection (mirrors order_blocks_mtf_v2.py)
│   ├── market_structure.py← BOS/CHoCH detection (mirrors market_structure_v1.py)
│   ├── fvg.py             ← Fair Value Gap detection (mirrors fvg_detector.py)
│   ├── liquidity_pools.py ← Liquidity pool clustering (mirrors liquidity_pools.py)
│   ├── ote.py             ← OTE 62-79% Fibonacci (mirrors ote_tracker.py)
│   ├── prev_high_low.py   ← Previous period H/L (mirrors prev_high_low.py)
│   ├── engulfing.py       ← Engulfing candles (mirrors engulfing_pro_v1.py)
│   └── breaker_blocks.py  ← Breaker blocks (mirrors breaker_blocks.py)
│
├── pipeline/              ← Event orchestration (NEW — Phase 1)
│   ├── __init__.py
│   ├── event_registry.py  ← Stateful active-event tracker
│   └── bar_processor.py   ← Multi-TF pipeline; labels bars with ConfluenceResult
│
├── strategies/
│   ├── ict/               ← ICT confluence strategy (NEW — Phase 1)
│   │   ├── __init__.py
│   │   └── confluence_strategy.py  ← NautilusTrader strategy using EventRegistry
│   ├── session/
│   │   └── asia_session_sweep.py   ← Existing (Sprint 05)
│   └── ...
│
└── core / analytics / data / ...  ← Existing infrastructure
```

---

## 3. Event Schema

### IndicatorEvent (dataclass)

| Field             | Type                          | Description |
|-------------------|-------------------------------|-------------|
| timestamp         | pd.Timestamp (UTC)            | **Bar close time of confirming bar** (anti-lookahead boundary) |
| symbol            | str                           | "XAUUSD" |
| timeframe         | str                           | "M5", "M15", "H1", etc. |
| direction         | Direction enum                | BULLISH / BEARISH / NEUTRAL |
| event_type        | EventType enum                | What concept fired |
| level_or_zone     | float \| (float, float)       | Price level or (lo, hi) zone |
| state             | EventState enum               | PENDING / ACTIVE / IN_ZONE / MITIGATED / EXPIRED |
| metadata          | dict                          | Indicator-specific extras |
| score_contribution| int                           | Pre-computed from SCORE_MATRIX |

### EventType Enum
`ORDER_BLOCK_ACTIVE`, `ORDER_BLOCK_MITIGATED`, `BOS`, `CHOCH`, `FVG_ACTIVE`, `FVG_MITIGATED`, `LIQUIDITY_POOL_FORMED`, `LIQUIDITY_POOL_SWEPT`, `OTE_ACTIVE`, `OTE_ENTERED`, `PREV_HIGH_FORMED`, `PREV_HIGH_BROKEN`, `PREV_LOW_BROKEN`, `SESSION_SWEEP`, `ENGULFING`, `BREAKER_BLOCK_FORMED`, `BREAKER_BLOCK_RETESTED`, `BREAKER_BLOCK_BROKEN`

### Score Matrix (from K's live confluence_scorer.py)
| Event Type         | D1 | H4 | H1 | M30 | M15 | M5 |
|--------------------|----|----|----|----|-----|-----|
| ORDER_BLOCK_ACTIVE | 2  | 2  | 2  | 2  | 1   | 1  |
| BOS                | 1  | 1  | 1  | 1  | 2   | 2  |
| CHOCH              | 1  | 1  | 1  | 1  | 1   | 1  |
| ENGULFING          | 0  | 0  | 1  | 2  | 2   | 2  |
| FVG_ACTIVE         | 1  | 1  | 1  | 1  | 1   | 1  |
| OTE_ENTERED        | —  | 1  | 1  | —  | 1   | 1  |
| BREAKER_BLOCK_*    | —  | —  | 1  | 1  | 1–2 | 1–2|
| SESSION_SWEEP      | —  | —  | —  | 1  | 2   | 2  |
| LIQUIDITY_SWEPT    | —  | 1  | 1  | 1  | 1   | 1  |

**MIN_FIRE_SCORE = 6** (matches live system as of 2026-03-12)

---

## 4. Research Flow

```
1. Data loading
   BarProcessor.load(["M15","H1","H4","D1"])
   → pd.DataFrame per timeframe, UTC-indexed

2. Indicator runs (vectorized, per-TF)
   order_blocks.detect_order_blocks(df_m15, ...)
   market_structure.detect_market_structure(df_h1, ...)
   fvg.detect_fvg(df_m15, ...)
   ... all 8 adapters × 4 timeframes
   → List[IndicatorEvent] per adapter/TF

3. Event registry
   EventRegistry.feed(all_events)  # sorted by timestamp
   → stateful active-event tracker

4. Bar labeling
   for bar in base_df.iterrows():
       result = registry.confluence_at(bar.timestamp)
       # result: ConfluenceResult with .score, .direction, .fire, .combo

5. Output
   labeled_bars.parquet   — per-bar confluence labels
   fire_events.csv        — only bars where fire=True
   pipeline_report.html   — HTML summary

6. Strategy backtesting (Phase 2)
   ICTConfluenceStrategy(config, registry)
   → NautilusTrader BacktestNode
   → positions.csv, scorecard.json
```

---

## 5. Session / Timezone Definitions

All times are UTC.  No Berlin offset is applied in computation.

| Session   | UTC Start | UTC End | Berlin CET Note |
|-----------|-----------|---------|-----------------|
| Asia      | 03:00     | 11:00   | 04:00–12:00 |
| London    | 11:00     | 16:00   | 12:00–17:00 |
| New York  | 16:00     | 23:00   | 17:00–00:00 |

ICT Kill Zones (UTC):
- Asia KZ: 01:00–03:00
- London KZ: 08:00–11:00
- NY KZ: 13:00–15:00

Asia Sweep Strategy (existing, mirrors sessions_model.py):
- Range window: 21:00–00:59 UTC (overnight wrap)
- Entry window: 01:00–04:59 UTC

---

## 6. Anti-Lookahead Rules

All rules are encoded in the indicator adapters.  See `schema.LOOKAHEAD_RULES` for machine-readable form.

| Indicator      | Rule |
|----------------|------|
| Order Blocks   | `activation_time = times[ob_idx + 1]` (next bar after impulse) |
| Market Structure| Fractal at index p visible at p + length (need right-side window) |
| FVG            | Formed at `times[i+1]` (3-bar pattern complete); mitigation from i+2 |
| Liquidity Pools| Pivot at p confirmed at p + swing_length |
| OTE            | InOTE set from current bar CLOSE; no future data |
| Engulfing      | bar[i] vs bar[i-1] only |
| Breaker Blocks | Only forms after OB mitigation is confirmed |
| Prev High/Low  | Prior completed period only; no intra-period data |

---

## 7. Parity Risks vs Live System

Items requiring investigation before treating backtest results as comparable to K's live performance:

| # | Risk | Severity | Notes |
|---|------|----------|-------|
| 1 | **Base TF** | High | Live system scans at M5 close (k_scanner_v2.py); backtest uses M15. Run M5 base_tf experiment. |
| 2 | **Execution timing** | Medium | Live enters at next-tick after M5 close; backtest enters at bar-close. ~5min slippage window. |
| 3 | **OB volume scoring** | Medium | ob_volume_scorer.py contestation % not yet wired. OBs currently unscored by volume. |
| 4 | **Min score threshold** | Low | Live MIN_FIRE_SCORE = 6 (raised 2026-03-12). Confirmed in schema.py. |
| 5 | **Spread/commission** | Low | Use $0.30/trade baseline (from Asia Sweep cost stress). |
| 6 | **Session sweep gate** | Medium | Live requires sweep at session open as a gate (not just a score boost). Need explicit gate logic. |

---

## 8. Next Runs

```bash
# Step 1: Run pipeline labeling (diagnostic — no backtest)
$env:PYTHONPATH="D:\.openclaw\GoldBacktesting\Solid2026"
python scripts/run_ict_event_pipeline.py

# Step 2: OB standalone validation (expect FAIL)
python scripts/run_ict_ob_standalone.py      # to be written in Phase 2

# Step 3: FVG standalone validation (expect FAIL)
python scripts/run_ict_fvg_standalone.py     # to be written in Phase 2

# Step 4: Full ICT confluence backtest
python scripts/run_ict_full_confluence.py    # to be written in Phase 2

# Step 5: Pending from Phase 0
python scripts/run_asia_sweep_validation.py  # Asia Sweep WFV (still pending)
```

---

## 9. Files Created (Phase 1)

| File | Purpose |
|------|---------|
| `src/gold_research/indicators/__init__.py` | Package init + schema re-exports |
| `src/gold_research/indicators/schema.py` | Core event dataclasses + score matrix |
| `src/gold_research/indicators/sessions.py` | Session windows (UTC) |
| `src/gold_research/indicators/order_blocks.py` | OB detector adapter |
| `src/gold_research/indicators/market_structure.py` | BOS/CHoCH adapter |
| `src/gold_research/indicators/fvg.py` | FVG adapter |
| `src/gold_research/indicators/liquidity_pools.py` | Liquidity pool adapter |
| `src/gold_research/indicators/ote.py` | OTE tracker adapter |
| `src/gold_research/indicators/prev_high_low.py` | Previous H/L adapter |
| `src/gold_research/indicators/engulfing.py` | Engulfing candle adapter |
| `src/gold_research/indicators/breaker_blocks.py` | Breaker block adapter |
| `src/gold_research/pipeline/__init__.py` | Package init |
| `src/gold_research/pipeline/event_registry.py` | Active event state tracker |
| `src/gold_research/pipeline/bar_processor.py` | Multi-TF pipeline orchestrator |
| `src/gold_research/strategies/ict/__init__.py` | Package init |
| `src/gold_research/strategies/ict/confluence_strategy.py` | NautilusTrader strategy |
| `scripts/run_ict_event_pipeline.py` | Pipeline runner + HTML report |
| `experiments/ict/ob_standalone.yaml` | OB-only experiment spec |
| `experiments/ict/fvg_standalone.yaml` | FVG-only experiment spec |
| `experiments/ict/full_confluence.yaml` | Full ICT confluence spec |
| `journal/architecture_ict.md` | This file |
| `results/raw_runs/ICT_PHASE1_FOUNDATION/milestone_report.html` | Milestone report |
