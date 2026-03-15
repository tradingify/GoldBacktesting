"""HTML dashboard reporting for runs and portfolios."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, UTC
from html import escape
from pathlib import Path
import json

from src.gold_research.core.paths import ProjectPaths
from src.gold_research.store.db import get_connection


@dataclass
class RunDashboardRow:
    """Human-facing summary of a canonical run."""

    run_id: str
    experiment_id: str
    strategy_name: str
    run_type: str | None
    status: str
    screening_status: str | None
    validation_status: str | None
    promotion_state: str | None
    total_trades: int
    sharpe: float
    profit_factor: float
    net_profit: float
    win_rate: float
    scorecard_path: str | None
    run_dir: Path
    validation_summary_path: str | None


def _report_root() -> Path:
    root = ProjectPaths.DATA / "manifests" / "reports" / "html"
    root.mkdir(parents=True, exist_ok=True)
    (root / "runs").mkdir(parents=True, exist_ok=True)
    (root / "portfolios").mkdir(parents=True, exist_ok=True)
    return root


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _fmt_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"${value:,.2f}"


def _css() -> str:
    return """
body { font-family: Arial, sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }
h1, h2, h3 { color: #0f172a; }
.meta { color: #475569; margin-bottom: 20px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0 24px; }
.card { background: white; border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px; min-width: 180px; }
.label { font-size: 12px; color: #64748b; text-transform: uppercase; }
.value { font-size: 22px; font-weight: bold; margin-top: 6px; }
table { border-collapse: collapse; width: 100%; background: white; }
th, td { border: 1px solid #cbd5e1; padding: 8px 10px; font-size: 14px; text-align: left; vertical-align: top; }
th { background: #e2e8f0; position: sticky; top: 0; }
.pass { color: #166534; font-weight: bold; }
.soft_fail { color: #92400e; font-weight: bold; }
.hard_fail, .failed, .rejected { color: #b91c1c; font-weight: bold; }
.candidate_for_portfolio, .completed { color: #1d4ed8; font-weight: bold; }
.mono { font-family: Consolas, monospace; font-size: 12px; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
ul { line-height: 1.5; }
"""


def _load_run_rows() -> list[RunDashboardRow]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT
                runs.run_id,
                runs.experiment_id,
                runs.strategy_class_path,
                runs.run_type,
                runs.status,
                promotions.promotion_state,
                screen.status AS screening_status,
                validation.status AS validation_status
            FROM runs
            LEFT JOIN promotions ON promotions.run_id = runs.run_id
            LEFT JOIN gate_results AS screen
                ON screen.run_id = runs.run_id AND screen.gate_name = 'screening'
            LEFT JOIN gate_results AS validation
                ON validation.run_id = runs.run_id AND validation.gate_name = 'validation'
            ORDER BY COALESCE(runs.completed_at, runs.started_at) DESC, runs.run_id DESC
            """
        ).fetchall()

    dashboard_rows: list[RunDashboardRow] = []
    for row in rows:
        row_dict = dict(row)
        strategy_name = row_dict["strategy_class_path"].rsplit(".", 1)[-1]
        run_dir = ProjectPaths.RESULTS / "raw_runs" / row_dict["experiment_id"] / row_dict["run_id"]
        scorecard_path = run_dir / "scorecard.json"
        validation_summary_path = run_dir / "validation_summary.json"
        scorecard = {}
        if scorecard_path.exists():
            scorecard = _read_json(scorecard_path)
        dashboard_rows.append(
            RunDashboardRow(
                run_id=row_dict["run_id"],
                experiment_id=row_dict["experiment_id"],
                strategy_name=strategy_name,
                run_type=row_dict["run_type"],
                status=row_dict["status"],
                screening_status=row_dict["screening_status"],
                validation_status=row_dict["validation_status"],
                promotion_state=row_dict["promotion_state"],
                total_trades=int(scorecard.get("total_trades", 0)),
                sharpe=float(scorecard.get("sharpe", 0.0)),
                profit_factor=float(scorecard.get("profit_factor", 0.0)),
                net_profit=float(scorecard.get("total_net_profit", 0.0)),
                win_rate=float(scorecard.get("win_rate", 0.0)),
                scorecard_path=str(scorecard_path) if scorecard_path.exists() else None,
                run_dir=run_dir,
                validation_summary_path=str(validation_summary_path) if validation_summary_path.exists() else None,
            )
        )
    return dashboard_rows


def _build_run_detail_page(row: RunDashboardRow, root: Path) -> str:
    scorecard = _read_json(Path(row.scorecard_path)) if row.scorecard_path else {}
    gate = _read_json(row.run_dir / "gate_results.json") if (row.run_dir / "gate_results.json").exists() else {}
    validation = _read_json(Path(row.validation_summary_path)) if row.validation_summary_path else {}
    out_path = root / "runs" / f"{row.run_id}.html"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Run Report - {escape(row.run_id)}</title>
<style>{_css()}</style>
</head>
<body>
<h1>Run Report</h1>
<div class="meta">{escape(row.run_id)} | {escape(row.strategy_name)} | {escape(row.experiment_id)}</div>
<div class="cards">
  <div class="card"><div class="label">Promotion</div><div class="value {escape((row.promotion_state or '').lower())}">{escape(row.promotion_state or '-')}</div></div>
  <div class="card"><div class="label">Sharpe</div><div class="value">{_fmt_float(row.sharpe)}</div></div>
  <div class="card"><div class="label">Net Profit</div><div class="value">{_fmt_money(row.net_profit)}</div></div>
  <div class="card"><div class="label">Trades</div><div class="value">{row.total_trades}</div></div>
</div>
<h2>Screening</h2>
<pre>{escape(json.dumps(gate, indent=2))}</pre>
<h2>Validation</h2>
<pre>{escape(json.dumps(validation, indent=2))}</pre>
<h2>Scorecard</h2>
<pre>{escape(json.dumps(scorecard, indent=2))}</pre>
<h2>Artifacts</h2>
<ul>
  <li><span class="mono">{escape(str(row.run_dir))}</span></li>
  <li><span class="mono">{escape(row.scorecard_path or '-')}</span></li>
  <li><span class="mono">{escape(row.validation_summary_path or '-')}</span></li>
</ul>
</body>
</html>"""
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


def _load_portfolios() -> list[dict]:
    with closing(get_connection()) as conn:
        portfolios = conn.execute(
            """
            SELECT portfolio_id, portfolio_type, selection_policy_json, allocation_policy_json, created_at
            FROM portfolios
            ORDER BY created_at DESC, portfolio_id DESC
            """
        ).fetchall()
        members = conn.execute(
            """
            SELECT portfolio_id, run_id, weight, role
            FROM portfolio_members
            ORDER BY portfolio_id, weight DESC
            """
        ).fetchall()

    members_by_portfolio: dict[str, list[dict]] = {}
    for row in members:
        row_dict = dict(row)
        members_by_portfolio.setdefault(row_dict["portfolio_id"], []).append(row_dict)

    result = []
    for row in portfolios:
        row_dict = dict(row)
        summary_path = ProjectPaths.RESULTS / "portfolios" / row_dict["portfolio_id"] / "portfolio_summary.json"
        summary = _read_json(summary_path) if summary_path.exists() else {}
        row_dict["members"] = members_by_portfolio.get(row_dict["portfolio_id"], [])
        row_dict["summary"] = summary
        row_dict["summary_path"] = str(summary_path) if summary_path.exists() else None
        result.append(row_dict)
    return result


def _build_portfolio_page(portfolio: dict, root: Path) -> str:
    out_path = root / "portfolios" / f"{portfolio['portfolio_id']}.html"
    metrics = portfolio.get("summary", {}).get("metrics", {})
    robustness = portfolio.get("summary", {}).get("robustness", {})
    members_html = "".join(
        f"<tr><td class='mono'>{escape(member['run_id'])}</td><td>{escape(member['role'])}</td><td>{float(member['weight']):.4f}</td></tr>"
        for member in portfolio.get("members", [])
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Portfolio Report - {escape(portfolio['portfolio_id'])}</title>
<style>{_css()}</style>
</head>
<body>
<h1>Portfolio Report</h1>
<div class="meta">{escape(portfolio['portfolio_id'])} | template: {escape(portfolio['portfolio_type'])}</div>
<div class="cards">
  <div class="card"><div class="label">Status</div><div class="value {escape(portfolio.get('summary', {}).get('status', '').lower())}">{escape(portfolio.get('summary', {}).get('status', '-'))}</div></div>
  <div class="card"><div class="label">Final Value</div><div class="value">{_fmt_money(metrics.get('portfolio_final_value'))}</div></div>
  <div class="card"><div class="label">Sharpe</div><div class="value">{_fmt_float(metrics.get('portfolio_sharpe'))}</div></div>
  <div class="card"><div class="label">Max Drawdown</div><div class="value">{_fmt_pct(metrics.get('portfolio_max_drawdown'))}</div></div>
</div>
<h2>Members</h2>
<table>
  <thead><tr><th>Run</th><th>Role</th><th>Weight</th></tr></thead>
  <tbody>{members_html}</tbody>
</table>
<h2>Robustness</h2>
<pre>{escape(json.dumps(robustness, indent=2))}</pre>
<h2>Artifacts</h2>
<ul>
  <li><span class="mono">{escape(portfolio.get('summary_path') or '-')}</span></li>
</ul>
</body>
</html>"""
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


class HtmlDashboardReport:
    """Build a human-friendly HTML overview of runs and portfolios."""

    @staticmethod
    def build_dashboard() -> dict[str, str]:
        root = _report_root()
        run_rows = _load_run_rows()
        run_links = {row.run_id: _build_run_detail_page(row, root) for row in run_rows}
        portfolios = _load_portfolios()
        portfolio_links = {
            portfolio["portfolio_id"]: _build_portfolio_page(portfolio, root)
            for portfolio in portfolios
        }

        tested = len(run_rows)
        passed = sum(1 for row in run_rows if row.validation_status == "pass")
        failed = sum(1 for row in run_rows if row.status == "failed")
        rejected = sum(1 for row in run_rows if row.promotion_state == "rejected")
        candidates = sum(1 for row in run_rows if row.promotion_state == "candidate_for_portfolio")

        rows_html = "".join(
            f"""
            <tr>
              <td class="mono"><a href="runs/{escape(row.run_id)}.html">{escape(row.run_id)}</a></td>
              <td>{escape(row.strategy_name)}</td>
              <td>{escape(row.experiment_id)}</td>
              <td>{escape(row.run_type or '-')}</td>
              <td class="{escape((row.status or '').lower())}">{escape(row.status)}</td>
              <td class="{escape((row.screening_status or '').lower())}">{escape(row.screening_status or '-')}</td>
              <td class="{escape((row.validation_status or '').lower())}">{escape(row.validation_status or '-')}</td>
              <td class="{escape((row.promotion_state or '').lower())}">{escape(row.promotion_state or '-')}</td>
              <td>{row.total_trades}</td>
              <td>{_fmt_float(row.sharpe)}</td>
              <td>{_fmt_float(row.profit_factor)}</td>
              <td>{_fmt_money(row.net_profit)}</td>
              <td>{_fmt_pct(row.win_rate)}</td>
            </tr>
            """
            for row in run_rows
        )
        portfolios_html = "".join(
            f"""
            <tr>
              <td><a href="portfolios/{escape(portfolio['portfolio_id'])}.html">{escape(portfolio['portfolio_id'])}</a></td>
              <td>{escape(portfolio['portfolio_type'])}</td>
              <td>{len(portfolio.get('members', []))}</td>
              <td>{_fmt_money(portfolio.get('summary', {}).get('metrics', {}).get('portfolio_final_value'))}</td>
              <td>{_fmt_float(portfolio.get('summary', {}).get('metrics', {}).get('portfolio_sharpe'))}</td>
              <td>{_fmt_pct(portfolio.get('summary', {}).get('metrics', {}).get('portfolio_max_drawdown'))}</td>
            </tr>
            """
            for portfolio in portfolios
        )
        dashboard_path = root / "index.html"
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gold Research Dashboard</title>
<style>{_css()}</style>
</head>
<body>
<h1>Gold Research Dashboard</h1>
<div class="meta">Generated on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
<div class="cards">
  <div class="card"><div class="label">Tested</div><div class="value">{tested}</div></div>
  <div class="card"><div class="label">Passed Validation</div><div class="value">{passed}</div></div>
  <div class="card"><div class="label">Failed</div><div class="value">{failed}</div></div>
  <div class="card"><div class="label">Rejected</div><div class="value">{rejected}</div></div>
  <div class="card"><div class="label">Portfolio Candidates</div><div class="value">{candidates}</div></div>
</div>
<h2>Master Run Table</h2>
<table>
  <thead>
    <tr>
      <th>Run</th><th>Strategy</th><th>Experiment</th><th>Type</th><th>Status</th>
      <th>Screening</th><th>Validation</th><th>Promotion</th><th>Trades</th>
      <th>Sharpe</th><th>PF</th><th>Net</th><th>Win Rate</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
<h2>Portfolios</h2>
<table>
  <thead>
    <tr><th>Portfolio</th><th>Template</th><th>Members</th><th>Final Value</th><th>Sharpe</th><th>Max DD</th></tr>
  </thead>
  <tbody>{portfolios_html}</tbody>
</table>
</body>
</html>"""
        dashboard_path.write_text(html, encoding="utf-8")
        return {
            "dashboard_path": str(dashboard_path),
            "run_count": str(tested),
            "portfolio_count": str(len(portfolios)),
            "runs_dir": str(root / "runs"),
            "portfolios_dir": str(root / "portfolios"),
        }
