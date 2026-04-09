#!/usr/bin/env python3
"""
Wave 2 Strategy Implementation Pipeline Summary
Scans all WAVE2 runs and reports pass/fail at each gate.
"""

import json
import os
from pathlib import Path
from datetime import datetime

RESULTS_DIR = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs")
MC3_OUTPUT = Path(r"D:\.openclaw\mission-control-3\B001\tasks.json")

def scan_wave2_runs():
    """Scan all WAVE2 experiment runs and collect gate results."""
    experiments = {}
    
    for exp_folder in RESULTS_DIR.iterdir():
        if not exp_folder.is_dir() or not exp_folder.name.startswith("WAVE2"):
            continue
        
        exp_id = exp_folder.name
        experiments[exp_id] = {
            "total_runs": 0,
            "screening_pass": 0,
            "screening_soft_fail": 0,
            "screening_fail": 0,
            "wfo_pass": 0,
            "wfo_fail": 0,
            "oos_pass": 0,
            "oos_fail": 0,
            "forward_pass": 0,
            "forward_fail": 0,
            "best_sharpe": 0,
            "best_pf": 0,
            "best_net": 0,
            "runs": []
        }
        
        for run_folder in exp_folder.iterdir():
            if not run_folder.is_dir():
                continue
            
            gate_file = run_folder / "gate_results.json"
            scorecard_file = run_folder / "scorecard.json"
            
            if not gate_file.exists() or not scorecard_file.exists():
                continue
            
            experiments[exp_id]["total_runs"] += 1
            
            # Load gate results
            with open(gate_file) as f:
                gate = json.load(f)
            
            # Load scorecard
            with open(scorecard_file) as f:
                scorecard = json.load(f)
            
            gate_status = gate.get("status", "unknown")
            gate_name = gate.get("gate_name", "unknown")
            
            # Track by gate type
            if gate_name == "screening":
                if gate_status == "pass":
                    experiments[exp_id]["screening_pass"] += 1
                elif gate_status == "soft_fail":
                    experiments[exp_id]["screening_soft_fail"] += 1
                else:
                    experiments[exp_id]["screening_fail"] += 1
            
            # Track best metrics
            sharpe = scorecard.get("sharpe", 0)
            pf = scorecard.get("profit_factor", 0)
            net = scorecard.get("total_net_profit", 0)
            
            if sharpe > experiments[exp_id]["best_sharpe"]:
                experiments[exp_id]["best_sharpe"] = sharpe
            if pf > experiments[exp_id]["best_pf"]:
                experiments[exp_id]["best_pf"] = pf
            if net > experiments[exp_id]["best_net"]:
                experiments[exp_id]["best_net"] = net
            
            # Store run details for top performers
            experiments[exp_id]["runs"].append({
                "run_id": run_folder.name,
                "gate": gate_name,
                "status": gate_status,
                "sharpe": sharpe,
                "pf": pf,
                "net": net,
                "trades": scorecard.get("total_trades", 0)
            })
    
    return experiments

def generate_report(experiments):
    """Generate plain text report for MC3."""
    lines = []
    lines.append("# WAVE 2 IMPLEMENTATION PIPELINE - STATUS REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M CET')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    for exp_id in sorted(experiments.keys()):
        exp = experiments[exp_id]
        total = exp["total_runs"]
        
        lines.append(f"## {exp_id}")
        lines.append("")
        lines.append(f"**Total Runs:** {total}")
        lines.append("")
        
        # Screening gate summary
        screen_pass = exp["screening_pass"]
        screen_soft = exp["screening_soft_fail"]
        screen_fail = exp["screening_fail"]
        screen_total = screen_pass + screen_soft + screen_fail
        
        if screen_total > 0:
            pass_pct = (screen_pass / screen_total) * 100
            lines.append(f"**Screening Gate:**")
            lines.append(f"- PASS: {screen_pass} ({pass_pct:.1f}%)")
            lines.append(f"- SOFT FAIL: {screen_soft}")
            lines.append(f"- FAIL: {screen_fail}")
            
            # Kill criteria check
            if screen_total > 0 and screen_pass == 0:
                lines.append(f"- VERDICT: **DEAD** (0% pass rate - no edge in this family)")
            elif screen_total > 0 and pass_pct < 10:
                lines.append(f"- WARNING: <10% pass rate - likely overfit or weak edge")
            else:
                lines.append(f"- Top performers advance to WFO validation")
        else:
            lines.append(f"**Screening Gate:** No screening results found")
        
        lines.append("")
        lines.append(f"**Best Metrics:**")
        lines.append(f"- Sharpe: {exp['best_sharpe']:.2f}")
        lines.append(f"- Profit Factor: {exp['best_pf']:.2f}")
        lines.append(f"- Net PnL: ${exp['best_net']:,.0f}")
        lines.append("")
        
        # Show top 3 runs by Sharpe
        sorted_runs = sorted(exp["runs"], key=lambda x: x["sharpe"], reverse=True)[:3]
        if sorted_runs:
            lines.append("**Top 3 Runs (by Sharpe):**")
            for i, run in enumerate(sorted_runs, 1):
                lines.append(f"{i}. Sharpe={run['sharpe']:.2f}, PF={run['pf']:.2f}, Trades={run['trades']}, Status={run['status']}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # Summary
    lines.append("## PIPELINE SUMMARY")
    lines.append("")
    total_experiments = len(experiments)
    dead_experiments = sum(1 for e in experiments.values() 
                          if e["screening_pass"] == 0 and e["total_runs"] > 0)
    survivors = total_experiments - dead_experiments
    
    lines.append(f"- **Experiments processed:** {total_experiments}")
    lines.append(f"- **Dead (0% screening pass):** {dead_experiments}")
    lines.append(f"- **Survivors advancing:** {survivors}")
    lines.append("")
    lines.append("### Next Steps")
    lines.append("1. Run WFO validation on screening survivors")
    lines.append("2. Run locked OOS on WFO survivors (WFE > 0.4)")
    lines.append("3. Run forward-test on OOS survivors")
    lines.append("4. Report final pass/fail to TGee for portfolio review")
    lines.append("")
    
    return "\n".join(lines)

def update_mc3_task(report_text):
    """Update MC3 task B001-005 with results."""
    # Load existing tasks
    tasks_file = MC3_OUTPUT
    if tasks_file.exists():
        with open(tasks_file) as f:
            tasks_data = json.load(f)
    else:
        tasks_data = {"project": "B001", "prefix": "B001", "owner": "Forge", "tasks": []}
    
    # Find or create task B001-005
    task_id = "B001-005"
    existing_task = None
    for task in tasks_data.get("tasks", []):
        if task.get("id") == task_id:
            existing_task = task
            break
    
    task_entry = {
        "id": task_id,
        "title": "Wave 2 Strategy Implementation Pipeline",
        "status": "in_progress",
        "owner": "Forge",
        "last_update": datetime.now().isoformat(),
        "summary": report_text[:2000],  # Truncate for JSON
        "details": "Full report in Solid2026/reports/wave2_summary.md"
    }
    
    if existing_task:
        existing_task.update(task_entry)
    else:
        tasks_data["tasks"].append(task_entry)
    
    # Write back
    with open(tasks_file, "w") as f:
        json.dump(tasks_data, f, indent=2)
    
    print(f"✅ Updated MC3 task {task_id}")

def main():
    print("[SCAN] Scanning Wave 2 runs...")
    experiments = scan_wave2_runs()
    
    if not experiments:
        print("[ERROR] No WAVE2 experiments found")
        return
    
    print(f"[INFO] Found {len(experiments)} Wave 2 experiments")
    
    report = generate_report(experiments)
    
    # Save full report
    report_path = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\reports\wave2_summary.md")
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"[OK] Full report saved to: {report_path}")
    
    # Update MC3
    update_mc3_task(report)
    
    # Print summary
    print("\n" + "="*60)
    print(report)

if __name__ == "__main__":
    main()
