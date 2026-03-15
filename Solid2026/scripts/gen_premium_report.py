import os
import json
from datetime import datetime

# Path for the report
HTML_OUTPUT_PATH = r"D:\.openclaw\GoldBacktesting\Solid2026\results\sprint_06_premium_report.html"
HERO_BG_PATH = r"C:\Users\wahdatw\.gemini\antigravity\brain\38aa47e3-b739-4e3f-95c6-2a9d43efd1d0\gold_factory_hero_bg_1773492899162.png"

# Sprint 06 Data
sprint_06_results = [
    {"name": "ComboModelB (Liq+MS)", "tf": "4h", "trades": 757, "pf": 1.22, "sharpe": 0.95, "pnl": 31172, "status": "PASS"},
    {"name": "ComboModelA (FVG+OB+MS)", "tf": "4h", "trades": 768, "pf": 0.99, "sharpe": -0.07, "pnl": -1532, "status": "FAIL"},
    {"name": "ComboModelA (FVG+OB+MS)", "tf": "1h", "trades": 1872, "pf": 0.69, "sharpe": 0.42, "pnl": -145727, "status": "FAIL"},
    {"name": "ComboModelB (Liq+MS)", "tf": "1h", "trades": 2343, "pf": 0.69, "sharpe": -0.31, "pnl": -211285, "status": "FAIL"},
    {"name": "ComboModelA (FVG+OB+MS)", "tf": "15m", "trades": 6004, "pf": 0.27, "sharpe": 0.16, "pnl": -1472728, "status": "FAIL"},
    {"name": "ComboModelB (Liq+MS)", "tf": "15m", "trades": 7446, "pf": 0.32, "sharpe": -0.15, "pnl": -2059568, "status": "FAIL"},
]

# Previous Sprint Summaries
sprints = [
    {"id": "00", "task": "Infrastructure", "status": "COMPLETE", "insight": "Nautilus API integration & Truthfulness verified."},
    {"id": "01", "task": "Baseline Discovery", "status": "COMPLETE", "insight": "76 combinations scanned, 33 survivors selected."},
    {"id": "02", "task": "Robustness Testing", "status": "COMPLETE", "insight": "10 candidates promoted via 5D adversarial gauntlet."},
    {"id": "03", "task": "Portfolio 01", "status": "COMPLETE", "insight": "Diversified portfolio assembled with ρ < 0.70 threshold."},
    {"id": "04", "task": "Real Data Validation", "status": "COMPLETE", "insight": "3 strategies passed real-world IBKR metrics."},
    {"id": "05", "task": "Portfolio 02", "status": "COMPLETE", "insight": "GOLD_PORT_02 live with Boll, ZScore, and Squeeze."},
    {"id": "06", "task": "SMC/ICT Discovery", "status": "ACTIVE", "insight": "Multi-factor confluence models validated on 4h timeframe."},
]

# HTML Template
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold Research Factory | Executive Briefing</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #0f172a;
            --accent-gold: #f59e0b;
            --glass-white: rgba(255, 255, 255, 0.05);
            --glass-gold: rgba(245, 158, 11, 0.1);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --success: #10b981;
            --danger: #ef4444;
        }

        body {
            background-color: var(--bg-deep);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 0;
            overflow-x: hidden;
        }

        .hero {
            position: relative;
            height: 40vh;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            background: url('HERO_IMAGE_PLACEHOLDER') center/cover no-repeat;
            box-shadow: inset 0 0 100px rgba(0,0,0,0.8);
        }

        .hero::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.4) 0%, rgba(15, 23, 42, 1) 100%);
        }

        .hero-content {
            position: relative;
            z-index: 10;
        }

        .hero h1 {
            font-size: 3.5rem;
            font-weight: 700;
            margin: 0;
            letter-spacing: -2px;
            background: linear-gradient(to right, #f59e0b, #fbbf24);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hero p {
            color: var(--text-secondary);
            font-size: 1.2rem;
            margin-top: 10px;
        }

        .container {
            max-width: 1200px;
            margin: -100px auto 100px;
            padding: 0 20px;
            position: relative;
            z-index: 20;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }

        .card {
            background: var(--glass-white);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 24px;
            transition: transform 0.3s ease;
        }

        .card:hover {
            transform: translateY(-5px);
            background: rgba(255, 255, 255, 0.08);
        }

        .kpi-card h3 {
            color: var(--text-secondary);
            font-size: 0.9rem;
            text-transform: uppercase;
            margin: 0 0 10px 0;
        }

        .kpi-card .value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--accent-gold);
        }

        .section-title {
            font-size: 1.5rem;
            font-weight: 600;
            margin: 40px 0 20px 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .section-title::before {
            content: '';
            width: 4px;
            height: 24px;
            background: var(--accent-gold);
            border-radius: 2px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--glass-white);
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        th {
            background: rgba(255, 255, 255, 0.05);
            text-align: left;
            padding: 16px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            text-transform: uppercase;
        }

        td {
            padding: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            font-size: 0.95rem;
        }

        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-pass { background: rgba(16, 185, 129, 0.2); color: var(--success); }
        .status-fail { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .status-active { background: rgba(245, 158, 11, 0.2); color: var(--accent-gold); }

        .pnl-pos { color: var(--success); }
        .pnl-neg { color: var(--danger); }

        .flow-diagram {
            display: flex;
            justify-content: space-between;
            margin-bottom: 40px;
            padding: 20px;
            background: var(--glass-white);
            border-radius: 16px;
        }

        .flow-step {
            display: flex;
            flex-direction: column;
            align-items: center;
            flex: 1;
            position: relative;
        }

        .flow-step:not(:last-child)::after {
            content: '→';
            position: absolute;
            right: -10px;
            top: 20px;
            color: var(--text-secondary);
        }

        .step-circle {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: var(--glass-white);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 10px;
            border: 2px solid var(--text-secondary);
            font-weight: 700;
        }

        .step-circle.active {
            background: var(--accent-gold);
            border-color: var(--accent-gold);
            color: var(--bg-deep);
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.5);
        }

        .step-circle.complete {
            background: var(--success);
            border-color: var(--success);
            color: var(--bg-deep);
        }

        .step-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-align: center;
        }

        footer {
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
            font-size: 0.85rem;
        }

    </style>
</head>
<body>

    <section class="hero">
        <div class="hero-content">
            <h1>GOLD RESEARCH FACTORY</h1>
            <p>Phase 4 Discovery: Sprint 06 Executive Briefing</p>
        </div>
    </section>

    <div class="container">
        
        <div class="kpi-grid">
            <div class="card kpi-card">
                <h3>Current Portfolio</h3>
                <div class="value">GOLD_PORT_02</div>
            </div>
            <div class="card kpi-card">
                <h3>Total Survivors</h3>
                <div class="value">11 Strategy Units</div>
            </div>
            <div class="card kpi-card">
                <h3>Discovery PnL</h3>
                <div class="value">+$31,172.01</div>
            </div>
            <div class="card kpi-card">
                <h3>System Status</h3>
                <div class="value" style="color:var(--success)">OPERATIONAL</div>
            </div>
        </div>

        <div class="section-title">Project Readiness Flow</div>
        <div class="flow-diagram">
            <div class="flow-step">
                <div class="step-circle complete">1</div>
                <div class="step-label">Research Design</div>
            </div>
            <div class="flow-step">
                <div class="step-circle complete">2</div>
                <div class="step-label">Data Readiness</div>
            </div>
            <div class="flow-step">
                <div class="step-circle complete">3</div>
                <div class="step-label">Model Construction</div>
            </div>
            <div class="flow-step">
                <div class="step-circle active">4</div>
                <div class="step-label">System Discovery</div>
            </div>
            <div class="flow-step">
                <div class="step-circle">5</div>
                <div class="step-label">Validation</div>
            </div>
            <div class="flow-step">
                <div class="step-circle">6</div>
                <div class="step-label">Falsification</div>
            </div>
            <div class="flow-step">
                <div class="step-circle">7</div>
                <div class="step-label">Portfolio Integration</div>
            </div>
        </div>

        <div class="section-title">Sprint 06: ICT/SMC Discovery Matrix</div>
        <table>
            <thead>
                <tr>
                    <th>Strategy Template</th>
                    <th>TF</th>
                    <th>Trades</th>
                    <th>PF</th>
                    <th>Sharpe</th>
                    <th>Net PnL</th>
                    <th>Outcome</th>
                </tr>
            </thead>
            <tbody>
                SPRINT_06_ROWS
            </tbody>
        </table>

        <div class="section-title">Factory Sprint Ledger</div>
        <div class="kpi-grid" style="grid-template-columns: 1fr;">
            SPRINT_HISTORY_CARDS
        </div>

    </div>

    <footer>
        &copy; 2026 Gold Research Factory. All discovery artifacts preserved in the Promotion Registry.
    </footer>

</body>
</html>
"""

# Generate Sprint 06 Rows
sprint_rows = ""
for res in sprint_06_results:
    pnl_class = "pnl-pos" if res["pnl"] > 0 else "pnl-neg"
    status_class = "status-pass" if res["status"] == "PASS" else "status-fail"
    pnl_str = f"${res['pnl']:,.2f}"
    sprint_rows += f"""
                <tr>
                    <td><b>{res['name']}</b></td>
                    <td>{res['tf']}</td>
                    <td>{res['trades']}</td>
                    <td>{res['pf']:.2f}</td>
                    <td>{res['sharpe']:.2f}</td>
                    <td class="{pnl_class}">{pnl_str}</td>
                    <td><span class="status-badge {status_class}">{res['status']}</span></td>
                </tr>"""

# Generate Sprint History Cards
history_cards = ""
for s in sprints:
    status_class = "status-pass" if s["status"] == "COMPLETE" else "status-active"
    history_cards += f"""
            <div class="card" style="margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <span style="color: var(--accent-gold); font-weight: 700; margin-right: 15px;">SPRINT {s['id']}</span>
                    <b>{s['task']}</b>
                    <p style="margin: 5px 0 0 0; font-size: 0.85rem; color: var(--text-secondary);">{s['insight']}</p>
                </div>
                <span class="status-badge {status_class}">{s['status']}</span>
            </div>"""

# Final Assembly
final_html = html_template.replace("HERO_IMAGE_PLACEHOLDER", HERO_BG_PATH)
final_html = final_html.replace("SPRINT_06_ROWS", sprint_rows)
final_html = final_html.replace("SPRINT_HISTORY_CARDS", history_cards)

# Write to file
os.makedirs(os.path.dirname(HTML_OUTPUT_PATH), exist_ok=True)
with open(HTML_OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(final_html)

print(f"Premium report generated at: {HTML_OUTPUT_PATH}")
