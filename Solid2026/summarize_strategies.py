import json
from pathlib import Path

# Load results
with open('data/manifests/reports/intakes/all_strategies_discovery_results.json') as f:
    results = json.load(f)

print("=" * 80)
print("SOLID2026 STRATEGY CATALOG — ALL DISCOVERY RESULTS")
print("=" * 80)
print()

# Group by strategy class
by_class = {}
for r in results:
    cls = r['strategy_class']
    if cls not in by_class:
        by_class[cls] = []
    by_class[cls].append(r)

print(f"Total Strategy Classes: {len(by_class)}")
print(f"Total Experiments: {len(results)}")
print()

# Summary table
print("-" * 80)
print(f"{'Strategy':<35} {'TF':<6} {'Best Sharpe':<12} {'Net Profit':<14} {'PF':<8} {'DD%':<10} {'Survivors'}")
print("-" * 80)

for cls in sorted(by_class.keys()):
    exps = by_class[cls]
    for exp in exps:
        tf = exp.get('timeframe', '?')
        sharpe = exp.get('best_sharpe') or 0
        profit = exp.get('best_net_profit') or 0
        pf = exp.get('best_profit_factor') or 0
        dd = abs(exp.get('best_max_dd_pct') or 0) * 100
        survivors = exp.get('screening_survivors') or 0
        
        sharpe_str = f"{sharpe:.3f}" if sharpe is not None else "N/A"
        profit_str = f"${profit:,.0f}" if profit is not None else "N/A"
        pf_str = f"{pf:.3f}" if pf is not None else "N/A"
        dd_str = f"{dd:.2f}%" if dd is not None else "N/A"
        
        print(f"{cls:<35} {tf:<6} {sharpe_str:<12} {profit_str:<14} {pf_str:<8} {dd_str:<10} {survivors}")

print("-" * 80)
print()

# Top 10 by Sharpe
print("=" * 80)
print("TOP 10 STRATEGY VARIANTS BY SHARPE")
print("=" * 80)

all_sorted = sorted(results, key=lambda x: x.get('best_sharpe') or -999, reverse=True)
for idx, r in enumerate(all_sorted[:10], 1):
    print(f"\n{idx}. {r['strategy_class']} ({r['timeframe']})")
    print(f"   Experiment: {r['experiment_id']}")
    print(f"   Best Sharpe: {r.get('best_sharpe', 'N/A'):.4f}" if r.get('best_sharpe') else "   Best Sharpe: N/A")
    print(f"   Net Profit: ${r.get('best_net_profit', 0):,.2f}")
    print(f"   Profit Factor: {r.get('best_profit_factor', 'N/A'):.3f}" if r.get('best_profit_factor') else "   Profit Factor: N/A")
    print(f"   Max DD: {abs(r.get('best_max_dd_pct', 0) or 0)*100:.2f}%")
    print(f"   Total Trades: {r.get('best_total_trades', 0):,}")
    print(f"   Win Rate: {(r.get('best_win_rate', 0) or 0)*100:.1f}%")
    print(f"   Screening: {r.get('screening_survivors', 0)} survivors / {r.get('screening_rejected', 0)} rejected / {r.get('screening_hold', 0)} hold")

print()
print("=" * 80)
print("STRATEGY CATEGORIES")
print("=" * 80)

# Categorize
categories = {
    'Trend': ['EMACross', 'ATRBreakout', 'DonchianBreakout', 'DualTimeframeTrendFilter'],
    'Mean Reversion': ['BollingerReversion', 'ZScoreReversion', 'VWAPReversion', 'RSIDivergence'],
    'Breakout': ['AsianTrapLondonBreakout', 'SqueezeBreakout', 'OpeningRangeBreakout'],
    'SMC/ICT': ['FVGReversal', 'ICTConfluence', 'ICTOrderBlockFVG', 'OrderBlockReturn'],
    'Session': ['AsiaSweep', 'AsiaSessionSweep'],
    'Hybrid': ['RegimeHybrid', 'ConfluenceScorer'],
    'Pullback': ['EMAPullback'],
    'Moving Average': ['MovingAverageCross'],
}

for cat, strategies in categories.items():
    print(f"\n{cat}:")
    for strat in strategies:
        matching = [r for r in results if strat.lower() in r['strategy_class'].lower()]
        if matching:
            for m in matching:
                sh = m.get('best_sharpe') or 0
                status = "✓ PASS" if sh >= 1.5 else ("~ HOLD" if sh >= 0.5 else "✗ FAIL")
                print(f"   - {m['strategy_class']} ({m['timeframe']}): Sharpe={sh:.3f} [{status}]")
