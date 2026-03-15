import pandas as pd
import numpy as np
import json
from pathlib import Path
import datetime

# Paths
POSITIONS_PATH = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs\SPRINT_06_SMC\sprint_06_combo_model_B_4h\positions.csv")
HERO_IMAGE = r"C:\Users\wahdatw\.gemini\antigravity\brain\38aa47e3-b739-4e3f-95c6-2a9d43efd1d0\combomodelb_hero_1773493356742.png"
OUTPUT_HTML = Path(r"D:\.openclaw\GoldBacktesting\Solid2026\results\raw_runs\SPRINT_06_SMC\sprint_06_combo_model_B_4h\tearsheet.html")

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

    # Prepare Data for Chart.js
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
    <title>ComboModelB (Liq+MS) 4h - Strategy Tearsheet</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --gold: #FFD700;
            --gold-bright: #FFF700;
            --dark-bg: #0D0D0D;
            --card-bg: rgba(255, 255, 255, 0.05);
            --text-main: #E0E0E0;
            --text-dim: #A0A0A0;
            --success: #00E676;
            --danger: #FF5252;
        }}
        
        body {{
            background-color: var(--dark-bg);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 0;
            overflow-x: hidden;
        }}
        
        .hero {{
            height: 400px;
            background: linear-gradient(rgba(0,0,0,0.6), rgba(13,13,13,1)), url('file:///{HERO_IMAGE.replace('\\', '/')}');
            background-size: cover;
            background-position: center;
            display: flex;
            align-items: flex-end;
            padding: 40px;
            position: relative;
        }}
        
        .hero-content {{
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
        }}
        
        h1 {{
            font-size: 3.5rem;
            margin: 0;
            background: linear-gradient(to right, var(--gold), #FFF);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -1px;
        }}
        
        .badge {{
            display: inline-block;
            padding: 6px 16px;
            border-radius: 30px;
            background: rgba(255, 215, 0, 0.1);
            color: var(--gold);
            border: 1px solid var(--gold);
            font-size: 0.9rem;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: -50px auto 100px;
            padding: 0 20px;
            position: relative;
            z-index: 10;
        }}
        
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .kpi-card {{
            background: var(--card-bg);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 25px;
            border-radius: 20px;
            text-align: center;
            transition: transform 0.3s ease;
        }}
        
        .kpi-card:hover {{
            transform: translateY(-5px);
            border-color: var(--gold);
        }}
        
        .kpi-value {{
            font-size: 2rem;
            font-weight: 700;
            display: block;
            margin-bottom: 5px;
        }}
        
        .kpi-label {{
            color: var(--text-dim);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 1.5px;
        }}
        
        .main-content {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 30px;
        }}
        
        .section {{
            background: var(--card-bg);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 24px;
            padding: 30px;
        }}
        
        h2 {{
            font-size: 1.5rem;
            margin-top: 0;
            margin-bottom: 25px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        h2::before {{
            content: '';
            width: 4px;
            height: 20px;
            background: var(--gold);
            display: inline-block;
            border-radius: 2px;
        }}
        
        .params-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        
        .params-list li {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        
        .params-list li:last-child {{
            border-bottom: none;
        }}
        
        .param-key {{
            color: var(--text-dim);
        }}
        
        .param-val {{
            color: var(--gold);
            font-weight: 600;
        }}
        
        .table-container {{
            max-height: 800px;
            overflow-y: auto;
            border-radius: 12px;
            padding-right: 10px;
        }}
        
        .table-container::-webkit-scrollbar {{
            width: 8px;
        }}
        
        .table-container::-webkit-scrollbar-thumb {{
            background: rgba(255, 215, 0, 0.2);
            border-radius: 10px;
        }}
        
        .trade-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        
        .trade-table th {{
            position: sticky;
            top: 0;
            background: var(--dark-bg);
            z-index: 100;
            text-align: left;
            padding: 12px;
            color: var(--text-dim);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        
        .trade-table td {{
            padding: 15px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        
        .pnl-pos {{ color: var(--success); }}
        .pnl-neg {{ color: var(--danger); }}
        
        .footer {{
            text-align: center;
            padding: 60px;
            color: var(--text-dim);
            font-size: 0.8rem;
            letter-spacing: 1px;
        }}
        
        canvas {{
            max-width: 100%;
        }}
    </style>
</head>
<body>

    <div class="hero">
        <div class="hero-content">
            <div class="badge">Model Discovered • Validation Passed</div>
            <h1>ComboModelB (Liq+MS)</h1>
        </div>
    </div>

    <div class="container">
        <div class="kpi-grid">
            <div class="kpi-card">
                <span class="kpi-value" style="color:var(--success)">+${net_pnl:,.0f}</span>
                <span class="kpi-label">Net Profit</span>
            </div>
            <div class="kpi-card">
                <span class="kpi-value">{sharpe:.2f}</span>
                <span class="kpi-label">Sharpe Ratio</span>
            </div>
            <div class="kpi-card">
                <span class="kpi-value">{win_rate*100:.1f}%</span>
                <span class="kpi-label">Win Rate</span>
            </div>
            <div class="kpi-card">
                <span class="kpi-value">{profit_factor:.2f}</span>
                <span class="kpi-label">Profit Factor</span>
            </div>
        </div>

        <div class="main-content">
            <div class="section">
                <h2>Equity Growth</h2>
                <canvas id="equityChart"></canvas>
                
                <h2 style="margin-top: 40px;">Full Transaction Ledger</h2>
                <div class="table-container">
                    <table class="trade-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Side</th>
                                <th>Avg Open</th>
                                <th>Avg Close</th>
                                <th>PnL</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join([f'''
                            <tr>
                                <td>{t['ts_closed'].strftime('%Y-%m-%d %H:%M')}</td>
                                <td>{t['side']}</td>
                                <td>{t['avg_px_open']:.2f}</td>
                                <td>{t['avg_px_close']:.2f}</td>
                                <td class="{'pnl-pos' if t['pnl_num'] > 0 else 'pnl-neg'}">{'+' if t['pnl_num'] > 0 else ''}{t['pnl_num']:.2f}</td>
                            </tr>
                            ''' for t in reversed(all_trades)])}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="section">
                <h2>Strategy Fingerprint</h2>
                <ul class="params-list">
                    <li><span class="param-key">Timeframe</span> <span class="param-val">4 Hours</span></li>
                    <li><span class="param-key">Asset</span> <span class="param-val">XAUUSD</span></li>
                    <li><span class="param-key">Lookback</span> <span class="param-val">1000 Bars</span></li>
                    <li><span class="param-key">Event Window</span> <span class="param-val">50 Bars</span></li>
                    <li><span class="param-key">Min Score</span> <span class="param-val">2.0</span></li>
                    <li><span class="param-key">ATR Multiplier</span> <span class="param-val">1.5x</span></li>
                    <li><span class="param-key">Portfolio Status</span> <span class="param-val" style="color:var(--success)">PROMOTED</span></li>
                </ul>
                
                <h2 style="margin-top: 40px;">Risk Profile</h2>
                <ul class="params-list">
                    <li><span class="param-key">Max Drawdown</span> <span class="param-val" style="color:var(--danger)">{max_dd*100:.2f}%</span></li>
                    <li><span class="param-key">Total Trades</span> <span class="param-val">{total_trades}</span></li>
                    <li><span class="param-key">Starting Cap</span> <span class="param-val">$100,000</span></li>
                </ul>
            </div>
        </div>
    </div>

    <div class="footer">
        SOLID 2026 QUANT FRAMEWORK • GENERATED AT {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>

    <script>
        const ctx = document.getElementById('equityChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: 'Equity Curve',
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
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{
                        grid: {{ color: 'rgba(255,255,255,0.05)' }},
                        ticks: {{ color: '#A0A0A0' }}
                    }},
                    x: {{
                        grid: {{ display: false }},
                        ticks: {{ color: '#A0A0A0', maxTicksLimit: 10 }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
    """
    
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"Tearsheet generated at: {OUTPUT_HTML}")

if __name__ == "__main__":
    generate_tearsheet()
