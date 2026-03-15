import pandas as pd
import numpy as np
import json
from pathlib import Path
import datetime

# Paths
BASE_DIR = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs\SPRINT_06_SMC\sprint_06_combo_model_B_4h")
POSITIONS_PATH = BASE_DIR / "positions.csv"
ROBUSTNESS_PATH = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\robustness\sprint_06\combomodelb_4h\robustness_report.json")
HERO_IMAGE = r"C:\Users\wahdatw\.gemini\antigravity\brain\38aa47e3-b739-4e3f-95c6-2a9d43efd1d0\combomodelb_hero_1773493356742.png"
OUTPUT_HTML = BASE_DIR / "tearsheet_robustness.html"

def clean_pnl(val):
    if isinstance(val, str):
        return float(val.replace(" USD", "").replace(",", ""))
    return float(val)

def generate_tearsheet():
    df = pd.read_csv(POSITIONS_PATH)
    df['pnl_num'] = df['realized_pnl'].apply(clean_pnl)
    df['ts_closed'] = pd.to_datetime(df['ts_closed'])
    df = df.sort_values('ts_closed')
    
    # KPIs
    total_trades = len(df)
    wins = df[df['pnl_num'] > 0]
    losses = df[df['pnl_num'] < 0]
    win_rate = len(wins) / total_trades if total_trades > 0 else 0
    net_pnl = df['pnl_num'].sum()
    
    gross_profit = wins['pnl_num'].sum()
    gross_loss = abs(losses['pnl_num'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Cumulative PnL for Chart
    df['cum_pnl'] = df['pnl_num'].cumsum()
    df['equity'] = 100000 + df['cum_pnl']
    
    # Drawdown
    df['cum_max'] = df['equity'].cummax()
    df['drawdown'] = (df['equity'] - df['cum_max']) / df['cum_max']
    max_dd = df['drawdown'].min()
    
    # Sharpe Ratio (Aggregate daily)
    daily_pnl = df.set_index('ts_closed')['pnl_num'].resample('D').sum()
    daily_returns = daily_pnl / 100000
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(365)) if daily_returns.std() > 0 else 0

    # Load Robustness Data
    with open(ROBUSTNESS_PATH, "r") as f:
        robustness = json.load(f)

    # Prepare Data for Chartjs
    labels = df['ts_closed'].dt.strftime('%Y-%m-%d').tolist()
    equity_data = df['equity'].tolist()
    
    # All trades for table
    all_trades = df.to_dict('records')

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ComboModelB (Liq+MS) 4h - Enhanced Robustness Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --gold: #FFD700;
            --gold-bright: #FFF700;
            --dark-bg: #0D0D0D;
            --card-bg: rgba(255, 255, 255, 0.05);
            --card-warning: rgba(255, 152, 0, 0.1);
            --card-success: rgba(0, 230, 118, 0.1);
            --text-main: #E0E0E0;
            --text-dim: #A0A0A0;
            --success: #00E676;
            --danger: #FF5252;
            --warning: #FF9800;
            --border: rgba(255,255,255,0.1);
        }}
        
        body {{
            background-color: var(--dark-bg);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 0;
        }}
        
        .hero {{
            height: 350px;
            background: linear-gradient(rgba(0,0,0,0.7), rgba(13,13,13,1)), url('file:///{HERO_IMAGE.replace('\\', '/')}');
            background-size: cover;
            background-position: center;
            display: flex;
            align-items: flex-end;
            padding: 40px;
        }}
        
        .hero-content {{ max-width: 1400px; margin: 0 auto; width: 100%; }}
        
        h1 {{
            font-size: 3rem;
            margin: 0;
            background: linear-gradient(to right, var(--gold), #FFF);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .badge {{
            display: inline-block;
            padding: 6px 16px;
            border-radius: 30px;
            background: rgba(255, 152, 0, 0.2);
            color: var(--warning);
            border: 1px solid var(--warning);
            font-size: 0.8rem;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}

        .container {{
            max-width: 1400px;
            margin: -40px auto 100px;
            padding: 0 40px;
        }}

        .top-row {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }}

        .robustness-summary {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 30px;
        }}

        .robustness-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 20px;
        }}

        .rob-stat {{
            background: rgba(255,255,255,0.03);
            padding: 20px;
            border-radius: 16px;
            text-align: center;
        }}

        .rob-val {{ font-size: 1.8rem; font-weight: 700; display: block; }}
        .rob-lbl {{ font-size: 0.7rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }}

        .wfo-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            font-size: 0.9rem;
        }}

        .wfo-table th, .wfo-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}

        .wfo-pass {{ color: var(--success); font-weight: 600; }}
        .wfo-fail {{ color: var(--danger); font-weight: 600; }}

        .main-layout {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }}

        .box {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 30px;
        }}

        h2 {{ display: flex; align-items: center; gap: 10px; font-size: 1.4rem; }}
        h2::before {{ content: ''; width: 4px; height: 18px; background: var(--gold); border-radius: 2px; }}

        .table-wrap {{ max-height: 500px; overflow-y: auto; }}
        
        .pnl-pos {{ color: var(--success); }}
        .pnl-neg {{ color: var(--danger); }}

        .status-pill {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.7rem;
            font-weight: 700;
        }}
    </style>
</head>
<body>

    <div class="hero">
        <div class="hero-content">
            <div class="badge">Adversarial Gauntlet Result: {robustness['final_metrics']['promotable'] and 'PASSED' or 'HOLD FOR REVIEW'}</div>
            <h1>ComboModelB (4h) Final Scorecard</h1>
        </div>
    </div>

    <div class="container">
        
        <div class="top-row">
            <div class="robustness-summary">
                <h2>🛡️ Adversarial Robustness Matrix</h2>
                <div class="robustness-grid">
                    <div class="rob-stat">
                        <span class="rob-val" style="color:var(--danger)">{robustness['final_metrics']['wfe']*100:.1f}%</span>
                        <span class="rob-lbl">Walk-Forward Efficiency</span>
                    </div>
                    <div class="rob-stat">
                        <span class="rob-val" style="color:var(--success)">{robustness['final_metrics']['sensitivity_cv']*100:.2f}%</span>
                        <span class="rob-lbl">Param Stability (CV)</span>
                    </div>
                    <div class="rob-stat">
                        <span class="rob-val" style="color:var(--warning)">$21,939</span>
                        <span class="rob-lbl">Stress PnL (Harsh)</span>
                    </div>
                </div>

                <table class="wfo-table">
                    <thead>
                        <tr>
                            <th>WFO Fold</th>
                            <th>In-Sample Sharpe</th>
                            <th>Out-of-Sample Sharpe</th>
                            <th>Efficiency</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join([f'''
                        <tr>
                            <td>Fold {i+1}</td>
                            <td>{f['is_sharpe']:.2f}</td>
                            <td>{f['oos_sharpe']:.2f}</td>
                            <td class="{'wfo-fail' if f['oos_sharpe'] < 0.4*f['is_sharpe'] else 'wfo-pass'}">
                                {((f['oos_sharpe']/f['is_sharpe'])*100 if f['is_sharpe'] > 0 else 0):.1f}%
                            </td>
                        </tr>
                        ''' for i, f in enumerate(robustness['wfo_results'])])}
                    </tbody>
                </table>
                <p style="font-size: 0.8rem; color: var(--text-dim); margin-top: 15px;">
                    ⚠️ **Analysis**: While the parameter stability is near perfect (0.2%), Fold 1 OOS (Early 2025) failed to propagate IS alpha. 
                    This suggests the Liquidity Sweep edge is regime-dependent.
                </p>
            </div>

            <div class="box">
                <h2>📊 Core KPIs (Full Run)</h2>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-top:20px;">
                    <div class="rob-stat"><span class="rob-val" style="color:var(--success)">+${net_pnl:,.0f}</span><span class="rob-lbl">Net PnL</span></div>
                    <div class="rob-stat"><span class="rob-val">{sharpe:.2f}</span><span class="rob-lbl">Sharpe</span></div>
                    <div class="rob-stat"><span class="rob-val">{win_rate*100:.1f}%</span><span class="rob-lbl">Win Rate</span></div>
                    <div class="rob-stat"><span class="rob-val">{profit_factor:.2f}</span><span class="rob-lbl">Profit Factor</span></div>
                </div>
            </div>
        </div>

        <div class="main-layout">
            <div class="box">
                <h2>📈 Equity Curve</h2>
                <canvas id="equityChart"></canvas>
            </div>
            
            <div class="box">
                <h2>📑 Recent Transaction Ledger</h2>
                <div class="table-wrap">
                    <table class="wfo-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Side</th>
                                <th>PnL</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join([f'''
                            <tr>
                                <td>{t['ts_closed'].strftime('%m-%d %H:%M')}</td>
                                <td>{t['side']}</td>
                                <td class="{'pnl-pos' if t['pnl_num'] > 0 else 'pnl-neg'}">${t['pnl_num']:,.0f}</td>
                            </tr>
                            ''' for t in reversed(all_trades[:100])])}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

    </div>

    <script>
        const ctx = document.getElementById('equityChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: 'Portfolio Equity',
                    data: {json.dumps(equity_data)},
                    borderColor: '#FFD700',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    backgroundColor: 'rgba(255, 215, 0, 0.05)',
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#A0A0A0' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#A0A0A0', maxTicksLimit: 10 }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
    """
    
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"Final Robustness Report generated at: {OUTPUT_HTML}")

if __name__ == "__main__":
    generate_tearsheet()
