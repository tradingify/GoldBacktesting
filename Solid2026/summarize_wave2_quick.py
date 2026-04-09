#!/usr/bin/env python3
"""
Wave 2 Strategy Implementation Pipeline Summary - Quick Version
"""

import json
import os
from pathlib import Path
from datetime import datetime

RESULTS_DIR = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs")
MC3_OUTPUT = Path(r"D:\.openclaw\mission-control-3\B001\tasks.json")

def quick_scan():
    """Quick scan of WAVE2 experiments."""
    results = []
    
    for exp_folder in RESULTS_DIR.iterdir():
        if not exp_folder.is_dir() or not exp_folder.name.startswith("WAVE2"):
            continue
        
        # Count runs
        run_count = len([f for f in exp_folder.iterdir() if f.is_dir()])
        
        # Sample first 10 runs for gate status
        sample_gates = {"screening": {"pass": 0, "soft_fail": 0, "fail": 0}}
        best_sharpe = 0
        best_pf = 0
        
        for i, run_folder in enumerate(exp_folder.iterdir()):
            if i >= 10:
                break
            if not run_folder.is_dir():
                continue
            
            gate_file = run_folder / "gate_results.json"
            scorecard_file = run_folder / "scorecard.json"
            
            if gate_file.exists():
                with open(gate_file) as f:
                    gate = json.load(f)
                gate_name = gate.get("gate_name", "unknown")
                status = gate.get("status", "unknown")
                if gate_name in sample_gates:
                    if status in sample_gates[gate_name]:
                        sample_gates[gate_name][status] += 1
            
            if scorecard_file.exists():
                with open(scorecard_file) as f:
                    sc = json.load(f)
                best_sharpe = max(best_sharpe, sc.get("sharpe", 0))
                best_pf = max(best_pf, sc.get("profit_factor", 0))
        
        results.append({
            "exp_id": exp_folder.name,
            "total_runs": run_count,
            "sample_screen_pass": sample_gates["screening"]["pass"],
            "sample_screen_soft": sample_gates["screening"]["soft_fail"],
            "sample_screen_fail": sample_gates["screening"]["fail"],
            "best_sharpe": best_sharpe,
            "best_pf": best_pf
        })
    
    return results

def generate_report(results):
    """Generate report."""
    lines = []
    lines.append("# WAVE 2 IMPLEMENTATION PIPELINE - STATUS REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M CET')}")
    lines.append("")
    lines.append("Note: Screening results based on sample of first 10 runs per experiment.")
    lines.append("")
    lines.append("-" * 60)
    lines.append("")
    
    for r in sorted(results, key=lambda x: x["exp_id"]):
        lines.append(f"## {r['exp_id']}")
        lines.append("")
        lines.append(f"**Total Runs:** {r['total_runs']}")
        lines.append("")
        
        sample_total = r["sample_screen_pass"] + r["sample_screen_soft"] + r["sample_screen_fail"]
        if sample_total > 0:
            pass_rate = (r["sample_screen_pass"] / sample_total) * 100
            lines.append(f"**Screening (sample of {sample_total} runs):**")
            lines.append(f"- PASS: {r['sample_screen_pass']} ({pass_rate:.0f}%)")
            lines.append(f"- SOFT FAIL: {r['sample_screen_soft']}")
            lines.append(f"- FAIL: {r['sample_screen_fail']}")
            
            if r["sample_screen_pass"] == 0:
                lines.append(f"- VERDICT: **DEAD** (0% pass rate)")
            elif pass_rate < 10:
                lines.append(f"- WARNING: <10% pass rate - likely overfit")
            else:
                lines.append(f"- STATUS: Advancing top performers to WFO")
        else:
            lines.append("**Screening:** No results found")
        
        lines.append("")
        lines.append(f"**Best Metrics (all runs):**")
        lines.append(f"- Sharpe: {r['best_sharpe']:.2f}")
        lines.append(f"- Profit Factor: {r['best_pf']:.2f}")
        lines.append("")
        lines.append("-" * 60)
        lines.append("")
    
    # Summary
    total_exp = len(results)
    dead = sum(1 for r in results if r["sample_screen_pass"] == 0 and r["total_runs"] > 0)
    
    lines.append("## PIPELINE SUMMARY")
    lines.append("")
    lines.append(f"- Experiments processed: {total_exp}")
    lines.append(f"- Dead (0% screening pass): {dead}")
    lines.append(f"- Survivors advancing: {total_exp - dead}")
    lines.append("")
    lines.append("### Next Steps")
    lines.append("1. Run WFO validation on screening survivors")
    lines.append("2. Run locked OOS on WFO survivors (WFE > 0.4)")
    lines.append("3. Run forward-test on OOS survivors")
    lines.append("4. Report final pass/fail to TGee for portfolio review")
    
    return "\n".join(lines)

def update_mc3(report_text):
    """Update MC3 task."""
    tasks_file = MC3_OUTPUT
    if tasks_file.exists():
        with open(tasks_file) as f:
            tasks_data = json.load(f)
    else:
        tasks_data = {"project": "B001", "prefix": "B001", "owner": "Forge", "tasks": []}
    
    task_id = "B001-005"
    task_entry = {
        "id": task_id,
        "title": "Wave 2 Strategy Implementation Pipeline",
        "status": "in_progress",
        "owner": "Forge",
        "last_update": datetime.now().isoformat(),
        "summary": report_text[:2000]
    }
    
    # Replace or add
    tasks_data["tasks"] = [t for t in tasks_data.get("tasks", []) if t.get("id") != task_id]
    tasks_data["tasks"].append(task_entry)
    
    with open(tasks_file, "w") as f:
        json.dump(tasks_data, f, indent=2)
    
    print(f"[OK] Updated MC3 task {task_id}")

def main():
    print("[SCAN] Scanning Wave 2 experiments...")
    results = quick_scan()
    
    if not results:
        print("[ERROR] No WAVE2 experiments found")
        return
    
    print(f"[INFO] Found {len(results)} Wave 2 experiments")
    
    report = generate_report(results)
    
    # Save report
    report_path = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\reports\wave2_summary.md")
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[OK] Report saved to: {report_path}")
    
    # Update MC3
    update_mc3(report)
    
    # Print
    print("\n" + "=" * 60)
    print(report)

if __name__ == "__main__":
    main()
