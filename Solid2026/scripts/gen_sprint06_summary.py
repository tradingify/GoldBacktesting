import json
from pathlib import Path
import datetime

# Paths
BASE_DIR = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs\SPRINT_06_SMC")
OUTPUT_HTML = BASE_DIR / "sprint_06_report.html"

def generate_sprint_report():
    scorecards = []
    for p in BASE_DIR.iterdir():
        score_path = p / "scorecard.json"
        if p.is_dir() and score_path.exists():
            with open(score_path, "r") as f:
                scorecards.append(json.load(f))
    
    # Sort by Net PnL or Sharpe
    scorecards.sort(key=lambda x: x.get('total_net_profit', 0), reverse=True)
    
    hero_bg = r"C:\Users\wahdatw\.gemini\antigravity\brain\38aa47e3-b739-4e3f-95c6-2a9d43efd1d0\gold_factory_hero_bg_1773492899162.png"

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sprint 06 Summary Report - SMC Discovery</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --gold: #FFD700;
            --dark-bg: #0A0A0A;
            --card-bg: rgba(255, 255, 255, 0.03);
            --text: #E0E0E0;
            --success: #00E676;
            --danger: #FF5252;
            --border: rgba(255,255,255,0.08);
        }}
        
        body {{
            background-color: var(--dark-bg);
            color: var(--text);
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 0;
        }}
        
        .header {{
            height: 300px;
            background: linear-gradient(rgba(0,0,0,0.8), rgba(10,10,10,1)), url('file:///{hero_bg.replace('\\', '/')}');
            background-size: cover;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
        }}
        
        h1 {{ font-size: 3.5rem; margin: 0; letter-spacing: -2px; color: var(--gold); }}
        
        .container {{ max-width: 1400px; margin: -50px auto 100px; padding: 0 40px; }}
        
        .stats-strip {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            padding: 30px;
            border-radius: 20px;
            text-align: center;
        }}
        
        .stat-val {{ font-size: 2rem; font-weight: 700; display: block; }}
        .stat-lbl {{ font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 1.5px; }}
        
        .comparison-table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card-bg);
            border-radius: 24px;
            overflow: hidden;
            border: 1px solid var(--border);
        }}
        
        .comparison-table th, .comparison-table td {{
            padding: 20px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        
        .comparison-table th {{ background: rgba(255,255,255,0.05); color: #888; font-size: 0.8rem; }}
        
        .winner-row {{ background: rgba(255, 215, 0, 0.05); }}
        .winner-row td {{ border-bottom-color: var(--gold); }}
        
        .verdict-pass {{ color: var(--success); font-weight: 700; }}
        .verdict-fail {{ color: var(--danger); font-weight: 700; opacity: 0.6; }}
        
        .footer {{ text-align: center; padding: 50px; color: #555; font-size: 0.8rem; }}
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>SPRINT 06: SMC DISCOVERY</h1>
            <p style="letter-spacing: 3px; color: #888;">STRATEGY COMBINATORIAL SCAN • 15 MODELS EVALUATED</p>
        </div>
    </div>

    <div class="container">
        <div class="stats-strip">
            <div class="stat-card"><span class="stat-val">15</span><span class="stat-lbl">Runs Executed</span></div>
            <div class="stat-card"><span class="stat-val" style="color:var(--success)">1</span><span class="stat-lbl">Candidates Promoted</span></div>
            <div class="stat-card"><span class="stat-val" style="color:var(--danger)">14</span><span class="stat-lbl">Rejections</span></div>
            <div class="stat-card"><span class="stat-val" style="color:var(--gold)">+$31,172</span><span class="stat-lbl">Max Single-Strategy PnL</span></div>
        </div>

        <table class="comparison-table">
            <thead>
                <tr>
                    <th>Strategy Run ID</th>
                    <th>Trades</th>
                    <th>Net PnL</th>
                    <th>Sharpe</th>
                    <th>Profit Factor</th>
                    <th>Max DD</th>
                    <th>Verdict</th>
                </tr>
            </thead>
            <tbody>
                {"".join([f'''
                <tr class="{'winner-row' if s['run_id'] == 'sprint_06_combo_model_B_4h' else ''}">
                    <td style="font-weight:600;">{s['run_id']}</td>
                    <td>{s['total_trades']}</td>
                    <td style="color:{'var(--success)' if s.get('total_net_profit',0) > 0 else 'var(--danger)'}">
                        ${s.get('total_net_profit', 0):,.0f}
                    </td>
                    <td>{s.get('sharpe', 0):.2f}</td>
                    <td>{s.get('profit_factor', 0):.2f}</td>
                    <td>{s.get('max_dd_pct', 0)*100:.1f}%</td>
                    <td class="{'verdict-pass' if s.get('total_net_profit',0) > 10000 else 'verdict-fail'}">
                        {s.get('total_net_profit',0) > 10000 and 'PASS' or 'FAIL'}
                    </td>
                </tr>
                ''' for s in scorecards])}
            </tbody>
        </table>

        <div style="margin-top: 50px;">
            <h2 style="color: var(--gold);">Sprint Key Insights</h2>
            <div style="background: var(--card-bg); padding: 30px; border-radius: 20px; border-left: 4px solid var(--gold);">
                <ul style="line-height: 1.8; color: #AAA;">
                    <li><strong>4h Timeframe Mastery</strong>: All 1h and 15m models were liquidated or heavily negative. The larger 4h window is critical for Liquidity and Market Structure signals to mature correctly.</li>
                    <li><strong>ComboModelB Edge</strong>: The combination of Liquidity Pools + Market Structure (Combo B) significantly outperformed Model A (which adds FVG/OrderBlocks). Model A's extra filters actually "killed" profitable trends.</li>
                    <li><strong>Execution Friction</strong>: High trade counts in lower timeframes (e.g. 2,343 trades for 1h Combo B) directly caused bankruptcy through friction, whereas 4h Combo B traded 757 times with positive expectancy.</li>
                </ul>
            </div>
        </div>
    </div>

    <div class="footer">
        SOLID 2026 QUANT FRAMEWORK • REPORT GENERATED {datetime.datetime.now().strftime('%Y-%m-%d')}
    </div>

</body>
</html>
    """
    
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"Sprint 06 Report generated at: {OUTPUT_HTML}")

if __name__ == "__main__":
    generate_sprint_report()
