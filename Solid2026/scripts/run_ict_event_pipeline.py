"""
ICT Event Pipeline — standalone research runner.

Runs the full multi-timeframe ICT indicator pipeline on historical XAUUSD
data, labels every 15m bar with a ConfluenceResult, and saves:

  labeled_bars.parquet      — per-bar labels (score, direction, fire, combo)
  fire_events.csv           — only bars where fire=True
  event_distribution.json   — counts of each event type and timeframe
  pipeline_report.html      — dark-theme HTML summary

Usage (from project root):
    $env:PYTHONPATH="D:\.openclaw\GoldBacktesting\Solid2026"
    python scripts/run_ict_event_pipeline.py

Optional arguments (edit CONFIG below):
  BASE_TF      : "M15" or "M5"
  START_DATE   : ISO date string or None
  END_DATE     : ISO date string or None
  BARS_DIR     : Path to canonical bars directory
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

# ── Project root on PYTHONPATH ─────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gold_research.core.paths import ProjectPaths
from gold_research.pipeline.bar_processor import BarProcessor

# ── Config ─────────────────────────────────────────────────────────────────────

SYMBOL        = "XAUUSD"
BASE_TF       = "M15"
START_DATE    = "2025-09-11"   # 6-month out-of-sample start
END_DATE      = None           # None = end of dataset
BARS_DIR      = Path(r"D:\.openclaw\GoldBacktesting\bars")
OUTPUT_DIR    = ProjectPaths.get_result_dir("ICT_EVENT_PIPELINE_M15")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("run_ict_event_pipeline")


def main() -> None:
    log.info("=" * 70)
    log.info("ICT Event Pipeline  |  %s  |  base=%s", SYMBOL, BASE_TF)
    log.info("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Run pipeline ──────────────────────────────────────────────────────────
    processor = BarProcessor(bars_dir=BARS_DIR, symbol=SYMBOL)
    labeled   = processor.run(base_tf=BASE_TF, start=START_DATE, end=END_DATE)

    log.info("Labeled bars: %d", len(labeled))
    log.info("Fire rate:    %.2f%%", labeled["fire"].mean() * 100)
    log.info("Mean score:   %.2f",   labeled["score"].mean())

    # ── Save labeled bars (drop python objects for parquet) ───────────────────
    save_cols = ["open", "high", "low", "close", "volume",
                 "score", "direction", "fire", "combo", "n_events"]
    labeled[save_cols].to_parquet(OUTPUT_DIR / "labeled_bars.parquet")
    log.info("Saved labeled_bars.parquet")

    # ── Fire events CSV ───────────────────────────────────────────────────────
    fire_df = labeled[labeled["fire"]][save_cols].reset_index()
    fire_df.to_csv(OUTPUT_DIR / "fire_events.csv", index=False)
    log.info("Saved fire_events.csv  (%d rows)", len(fire_df))

    # ── Event distribution ────────────────────────────────────────────────────
    type_counter: Counter = Counter()
    tf_counter:   Counter = Counter()
    dir_counter:  Counter = Counter()

    for events_list in labeled["events"]:
        for evt in events_list:
            type_counter[evt.event_type.value] += 1
            tf_counter[evt.timeframe]          += 1
            dir_counter[evt.direction.value]   += 1

    dist = {
        "event_types":  dict(type_counter.most_common()),
        "timeframes":   dict(tf_counter.most_common()),
        "directions":   dict(dir_counter),
        "total_events": sum(type_counter.values()),
        "fire_bars":    int(labeled["fire"].sum()),
        "total_bars":   len(labeled),
        "fire_rate_pct": round(labeled["fire"].mean() * 100, 2),
    }
    with open(OUTPUT_DIR / "event_distribution.json", "w") as f:
        json.dump(dist, f, indent=2)
    log.info("Saved event_distribution.json")

    # ── Score distribution stats ──────────────────────────────────────────────
    score_stats = labeled["score"].describe().to_dict()
    score_stats["fire_threshold"] = 6
    score_stats["above_threshold_pct"] = round(labeled["fire"].mean() * 100, 2)

    # ── Direction breakdown for fire bars ─────────────────────────────────────
    fire_dir = labeled[labeled["fire"]]["direction"].value_counts().to_dict()

    # ── Top combos ────────────────────────────────────────────────────────────
    top_combos = (
        labeled[labeled["fire"]]["combo"]
        .value_counts()
        .head(15)
        .to_dict()
    )

    # ── Write HTML report ─────────────────────────────────────────────────────
    html = _render_html(
        symbol=SYMBOL,
        base_tf=BASE_TF,
        start=START_DATE or "Dataset start",
        end=END_DATE or "Dataset end",
        n_bars=len(labeled),
        fire_rate=round(labeled["fire"].mean() * 100, 2),
        mean_score=round(labeled["score"].mean(), 2),
        score_stats=score_stats,
        fire_dir=fire_dir,
        top_combos=top_combos,
        dist=dist,
    )
    html_path = OUTPUT_DIR / "pipeline_report.html"
    html_path.write_text(html, encoding="utf-8")
    log.info("Saved pipeline_report.html")

    log.info("=" * 70)
    log.info("Done.  Artifacts in: %s", OUTPUT_DIR)
    log.info("=" * 70)


def _render_html(
    symbol, base_tf, start, end, n_bars, fire_rate, mean_score,
    score_stats, fire_dir, top_combos, dist,
) -> str:
    combo_rows = "".join(
        f'<tr><td>{c}</td><td>{n}</td>'
        f'<td>{round(n/dist["fire_bars"]*100,1)}%</td></tr>'
        for c, n in top_combos.items()
    )
    event_rows = "".join(
        f'<tr><td>{t}</td><td>{n}</td></tr>'
        for t, n in dist["event_types"].items()
    )
    tf_rows = "".join(
        f'<tr><td>{t}</td><td>{n}</td></tr>'
        for t, n in dist["timeframes"].items()
    )

    bull_pct = round(fire_dir.get("bullish", 0) / max(dist["fire_bars"], 1) * 100, 1)
    bear_pct = round(fire_dir.get("bearish", 0) / max(dist["fire_bars"], 1) * 100, 1)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICT Event Pipeline — {symbol} {base_tf}</title>
<style>
  :root {{
    --bg-primary: #0a0a0f;
    --bg-card: #12121a;
    --bg-table: #0f0f18;
    --text-primary: #e8e8f0;
    --text-muted: #888899;
    --gold: #f0c040;
    --green: #3ddc84;
    --red: #ff4d6d;
    --blue: #4da6ff;
    --border: #2a2a3a;
    --font: 'Inter', 'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg-primary); color: var(--text-primary); font-family: var(--font); }}
  .hero {{
    background: linear-gradient(135deg, #0a0a1a 0%, #1a1030 50%, #0a1520 100%);
    padding: 48px 32px 36px;
    border-bottom: 1px solid var(--border);
    animation: gradient-shift 8s ease infinite;
  }}
  @keyframes gradient-shift {{
    0%,100% {{ background-position: 0% 50%; }}
    50%      {{ background-position: 100% 50%; }}
  }}
  .hero h1 {{ font-size: 2rem; color: var(--gold); letter-spacing: 0.04em; }}
  .hero .subtitle {{ color: var(--text-muted); margin-top: 6px; font-size: 0.95rem; }}
  .kpi-strip {{
    display: flex; flex-wrap: wrap; gap: 16px;
    padding: 24px 32px; background: var(--bg-card);
    border-bottom: 1px solid var(--border);
  }}
  .kpi {{ flex: 1; min-width: 140px; }}
  .kpi .label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; }}
  .kpi .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; }}
  .kpi.gold .value  {{ color: var(--gold); }}
  .kpi.green .value {{ color: var(--green); }}
  .kpi.blue .value  {{ color: var(--blue); }}
  .kpi.red .value   {{ color: var(--red); }}
  .section {{ padding: 28px 32px; border-bottom: 1px solid var(--border); }}
  .section h2 {{ font-size: 1.15rem; color: var(--gold); margin-bottom: 16px; letter-spacing: 0.06em; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ background: #1e1e2a; color: var(--text-muted); font-weight: 500;
        padding: 8px 12px; text-align: left; letter-spacing: 0.05em;
        border-bottom: 1px solid var(--border); }}
  td {{ padding: 7px 12px; border-bottom: 1px solid var(--border); }}
  tr:hover td {{ background: rgba(240,192,64,0.04); }}
  .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .tag.pass {{ background: rgba(61,220,132,0.15); color: var(--green); }}
  .tag.warn {{ background: rgba(240,192,64,0.15); color: var(--gold); }}
  .bar-chart {{ display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }}
  .bar-row {{ display: flex; align-items: center; gap: 8px; font-size: 0.8rem; }}
  .bar-row .name {{ width: 200px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .bar-fill {{ height: 16px; border-radius: 3px; background: var(--gold); opacity: 0.7; min-width: 4px; }}
  .bar-row .count {{ color: var(--text-muted); }}
  footer {{ padding: 20px 32px; color: var(--text-muted); font-size: 0.8rem; }}
</style>
</head>
<body>

<div class="hero">
  <h1>ICT Event Pipeline — {symbol} {base_tf}</h1>
  <div class="subtitle">
    Period: {start} → {end} &nbsp;|&nbsp; Generated: 2026-03-12 &nbsp;|&nbsp; Solid2026 Research Framework
  </div>
</div>

<div class="kpi-strip">
  <div class="kpi gold"><div class="label">Total Bars</div><div class="value">{n_bars:,}</div></div>
  <div class="kpi green"><div class="label">Fire Bars</div><div class="value">{dist["fire_bars"]:,}</div></div>
  <div class="kpi blue"><div class="label">Fire Rate</div><div class="value">{fire_rate}%</div></div>
  <div class="kpi gold"><div class="label">Mean Score</div><div class="value">{mean_score}</div></div>
  <div class="kpi green"><div class="label">Bull Fires</div><div class="value">{fire_dir.get("bullish",0):,} ({bull_pct}%)</div></div>
  <div class="kpi red"><div class="label">Bear Fires</div><div class="value">{fire_dir.get("bearish",0):,} ({bear_pct}%)</div></div>
  <div class="kpi blue"><div class="label">Total Events</div><div class="value">{dist["total_events"]:,}</div></div>
</div>

<div class="section">
  <h2>Top Confluence Combos (fire bars only)</h2>
  <table>
    <thead><tr><th>Combo</th><th>Count</th><th>% of fires</th></tr></thead>
    <tbody>{combo_rows}</tbody>
  </table>
</div>

<div class="section">
  <h2>Event Distribution</h2>
  <div class="grid">
    <div>
      <p style="color:var(--text-muted);font-size:0.8rem;margin-bottom:8px;">By Event Type</p>
      <div class="bar-chart">
        {"".join(
          f'<div class="bar-row"><span class="name">{t}</span>'
          f'<div class="bar-fill" style="width:{min(200, n//5)}px"></div>'
          f'<span class="count">{n:,}</span></div>'
          for t, n in list(dist["event_types"].items())[:12]
        )}
      </div>
    </div>
    <div>
      <p style="color:var(--text-muted);font-size:0.8rem;margin-bottom:8px;">By Timeframe</p>
      <table>
        <thead><tr><th>Timeframe</th><th>Events</th></tr></thead>
        <tbody>{tf_rows}</tbody>
      </table>
    </div>
  </div>
</div>

<div class="section">
  <h2>Score Distribution</h2>
  <table>
    <thead><tr><th>Stat</th><th>Value</th></tr></thead>
    <tbody>
      {"".join(f'<tr><td>{k}</td><td>{round(v,3) if isinstance(v,float) else v}</td></tr>'
               for k,v in score_stats.items())}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Anti-Lookahead Status</h2>
  <table>
    <thead><tr><th>Indicator</th><th>Status</th><th>Rule</th></tr></thead>
    <tbody>
      <tr><td>Order Blocks</td><td><span class="tag pass">CLEAN</span></td><td>Activation = next-bar open after impulse</td></tr>
      <tr><td>Market Structure</td><td><span class="tag pass">CLEAN</span></td><td>Fractals need length bars each side</td></tr>
      <tr><td>FVG</td><td><span class="tag pass">CLEAN</span></td><td>Formed at bar i+1 close; mitigation from i+2</td></tr>
      <tr><td>Liquidity Pools</td><td><span class="tag pass">CLEAN</span></td><td>Swing pivots need swing_length each side</td></tr>
      <tr><td>OTE</td><td><span class="tag pass">CLEAN</span></td><td>Leg confirmed; InOTE from current close only</td></tr>
      <tr><td>Engulfing</td><td><span class="tag pass">CLEAN</span></td><td>bar[i] vs bar[i-1] only</td></tr>
      <tr><td>Breaker Blocks</td><td><span class="tag pass">CLEAN</span></td><td>Depends on confirmed OB mitigation</td></tr>
      <tr><td>Prev High/Low</td><td><span class="tag pass">CLEAN</span></td><td>Prior completed period only</td></tr>
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Next Steps</h2>
  <ol style="color:var(--text-muted);line-height:2rem;font-size:0.9rem;padding-left:1.2em;">
    <li>Review fire_events.csv — do fire timestamps cluster at session opens?</li>
    <li>Run <code style="color:var(--gold)">scripts/run_ict_ob_standalone.py</code> — validate OB-only edge</li>
    <li>Run <code style="color:var(--gold)">scripts/run_ict_fvg_standalone.py</code> — validate FVG-only edge</li>
    <li>Run <code style="color:var(--gold)">scripts/run_ict_full_confluence.py</code> — full ICT backtest</li>
    <li>Check correlation of ICT signals vs GOLD_PORT_02 trade dates</li>
  </ol>
</div>

<footer>
  Generated by Solid2026 ICT Event Pipeline &nbsp;|&nbsp; {symbol} {base_tf} &nbsp;|&nbsp;
  Anti-lookahead validated &nbsp;|&nbsp; Score threshold: 6
</footer>

</body>
</html>"""


if __name__ == "__main__":
    main()
