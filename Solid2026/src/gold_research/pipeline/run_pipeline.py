"""Canonical single-run pipeline for trustworthy backtest execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import traceback
import json

import pandas as pd

from src.gold_research.analytics.metrics import calmar_ratio, max_drawdown, sharpe_ratio, sortino_ratio
from src.gold_research.analytics.scorecards import StrategyScorecard
from src.gold_research.backtests.engine.nautilus_runner import NautilusRunner
from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.core.artifacts import (
    build_run_manifest,
    get_run_dir,
    write_dataframe_csv,
    write_json,
)
from src.gold_research.core.config import save_yaml
from src.gold_research.gates.screening import evaluate_screening
from src.gold_research.store.promotions_repo import PromotionsRepository
from src.gold_research.store.runs_repo import RunsRepository, utc_now_iso
from src.gold_research.validation.automation import run_automatic_validation


@dataclass
class PipelineResult:
    """High-level result returned by the canonical run pipeline."""

    run_id: str
    experiment_id: str
    status: str
    run_dir: Path
    scorecard: StrategyScorecard
    artifacts: dict[str, str]
    error_text: str | None = None


def _parse_money_like(value: object) -> float:
    """Parse numeric or Nautilus money-like values into a plain float."""
    if value is None:
        return 0.0
    text = str(value).replace(",", "").strip()
    if " " in text:
        text = text.split(" ", 1)[0]
    return float(text)


def _safe_report(engine: object, method_name: str, *args: object) -> pd.DataFrame:
    """Call an engine report method defensively and normalize the result."""
    try:
        report = getattr(engine.trader, method_name)(*args)
    except Exception:
        return pd.DataFrame()
    return report if isinstance(report, pd.DataFrame) else pd.DataFrame()


def _build_scorecard(run_id: str, positions_report: pd.DataFrame) -> tuple[StrategyScorecard, pd.Series]:
    """Create a real scorecard from realized position PnL."""
    if positions_report.empty:
        return (
            StrategyScorecard(
                run_id=run_id,
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                total_net_profit=0.0,
                sharpe=0.0,
                sortino=0.0,
                calmar=0.0,
                max_dd_pct=0.0,
                status="NO_TRADES",
            ),
            pd.Series(dtype=float),
        )

    pnl_column = None
    for candidate in ("realized_pnl", "pnl"):
        if candidate in positions_report.columns:
            pnl_column = candidate
            break

    if pnl_column is None:
        return (
            StrategyScorecard(
                run_id=run_id,
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                total_net_profit=0.0,
                sharpe=0.0,
                sortino=0.0,
                calmar=0.0,
                max_dd_pct=0.0,
                status="COMPLETED_LIMITED_DATA",
            ),
            pd.Series(dtype=float),
        )

    pnl_series = positions_report[pnl_column].apply(_parse_money_like).astype(float)
    winners = pnl_series[pnl_series > 0]
    losers = pnl_series[pnl_series <= 0]
    gross_profit = float(winners.sum()) if not winners.empty else 0.0
    gross_loss = abs(float(losers.sum())) if not losers.empty else 0.0
    total_trades = int(len(pnl_series))
    win_rate = float(len(winners) / total_trades) if total_trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.99 if gross_profit > 0 else 0.0)
    net_profit = gross_profit - gross_loss

    equity_series = 100000.0 + pnl_series.cumsum()
    if total_trades > 0:
        equity_series.index = range(1, len(equity_series) + 1)
    returns = equity_series.pct_change().dropna()

    scorecard = StrategyScorecard(
        run_id=run_id,
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=float(min(profit_factor, 999.99)),
        total_net_profit=net_profit,
        sharpe=sharpe_ratio(returns) if not returns.empty else 0.0,
        sortino=sortino_ratio(returns) if not returns.empty else 0.0,
        calmar=calmar_ratio(returns, equity_series) if not returns.empty else 0.0,
        max_dd_pct=max_drawdown(equity_series) if not equity_series.empty else 0.0,
        status="COMPLETED",
    )
    return scorecard, equity_series


def run_single_pipeline(spec: ExperimentSpec) -> PipelineResult:
    """Execute a single run, persist canonical artifacts, and track state in SQLite."""
    return run_single_pipeline_with_context(spec)


def run_single_pipeline_with_context(
    spec: ExperimentSpec,
    *,
    parent_run_id: str | None = None,
    run_type: str | None = "single",
    fingerprint: str | None = None,
) -> PipelineResult:
    """Execute a single run with optional lineage and dedupe metadata."""
    repo = RunsRepository()
    run_dir = get_run_dir(spec.experiment_id, spec.run_id)
    repo.upsert_run(
        run_id=spec.run_id,
        experiment_id=spec.experiment_id,
        parent_run_id=parent_run_id,
        run_type=run_type,
        fingerprint=fingerprint,
        status="running",
        strategy_class_path=spec.strategy_class_path,
        dataset_manifest_id=spec.dataset.manifest_id,
        timeframe=spec.strategy_params.get("timeframe", spec.dataset.instrument_id),
        started_at=utc_now_iso(),
    )

    artifact_paths: dict[str, str] = {}
    try:
        runner = NautilusRunner(spec)
        results = runner.run()
        engine = results.get("engine")

        positions_report = results.get("positions_report")
        if not isinstance(positions_report, pd.DataFrame):
            positions_report = _safe_report(engine, "generate_positions_report")
        fills_report = results.get("fills_report")
        if not isinstance(fills_report, pd.DataFrame):
            fills_report = _safe_report(engine, "generate_order_fills_report")

        scorecard, equity_series = _build_scorecard(spec.run_id, positions_report)

        spec_path = run_dir / "spec.yaml"
        save_yaml(spec.model_dump(), spec_path)
        artifact_paths["spec"] = str(spec_path)

        scorecard_path = write_json(run_dir / "scorecard.json", scorecard.model_dump())
        artifact_paths["scorecard"] = str(scorecard_path)

        metrics_payload = {
            "run_id": spec.run_id,
            "experiment_id": spec.experiment_id,
            "status": scorecard.status,
            "metrics": {
                "total_trades": scorecard.total_trades,
                "win_rate": scorecard.win_rate,
                "profit_factor": scorecard.profit_factor,
                "total_net_profit": scorecard.total_net_profit,
                "sharpe": scorecard.sharpe,
                "sortino": scorecard.sortino,
                "calmar": scorecard.calmar,
                "max_dd_pct": scorecard.max_dd_pct,
            },
        }
        metrics_path = write_json(run_dir / "metrics.json", metrics_payload)
        artifact_paths["metrics"] = str(metrics_path)

        fills_path = write_dataframe_csv(run_dir / "fills.csv", fills_report)
        if fills_path:
            artifact_paths["fills"] = str(fills_path)

        positions_path = write_dataframe_csv(run_dir / "positions.csv", positions_report)
        if positions_path:
            artifact_paths["positions"] = str(positions_path)

        if not equity_series.empty:
            equity_df = pd.DataFrame({"equity": equity_series.astype(float)})
            equity_path = write_dataframe_csv(run_dir / "equity.csv", equity_df)
            if equity_path:
                artifact_paths["equity"] = str(equity_path)

        manifest = build_run_manifest(
            run_id=spec.run_id,
            experiment_id=spec.experiment_id,
            dataset_manifest_id=spec.dataset.manifest_id,
            strategy_class_path=spec.strategy_class_path,
            strategy_params=spec.strategy_params,
            timeframe=spec.strategy_params.get("timeframe"),
            status=scorecard.status,
            artifact_paths=artifact_paths,
        )
        manifest_path = write_json(run_dir / "run_manifest.json", manifest)
        artifact_paths["run_manifest"] = str(manifest_path)

        screening_decision = evaluate_screening(scorecard)
        gate_payload = {
            "run_id": spec.run_id,
            "gate_name": screening_decision.gate_name,
            "status": screening_decision.status,
            "score": screening_decision.score,
            "promotion_state": screening_decision.promotion_state,
            "reason": screening_decision.reason,
            "details": screening_decision.details,
        }
        gate_results_path = write_json(run_dir / "gate_results.json", gate_payload)
        artifact_paths["gate_results"] = str(gate_results_path)

        promotions_repo = PromotionsRepository()
        promotions_repo.upsert_gate_result(
            run_id=spec.run_id,
            gate_name=screening_decision.gate_name,
            status=screening_decision.status,
            score=screening_decision.score,
            details=gate_payload,
        )
        promotions_repo.upsert_promotion(
            run_id=spec.run_id,
            promotion_state=screening_decision.promotion_state,
            reason=screening_decision.reason,
        )

        validation_payload = run_automatic_validation(
            spec,
            run_dir=run_dir,
            screening_status=screening_decision.status,
            run_type=run_type,
        )
        validation_summary_path = run_dir / "validation_summary.json"
        if validation_summary_path.exists():
            artifact_paths["validation_summary"] = str(validation_summary_path)

        repo.upsert_run(
            run_id=spec.run_id,
            experiment_id=spec.experiment_id,
            parent_run_id=parent_run_id,
            run_type=run_type,
            fingerprint=fingerprint,
            status=scorecard.status.lower(),
            strategy_class_path=spec.strategy_class_path,
            dataset_manifest_id=spec.dataset.manifest_id,
            timeframe=spec.strategy_params.get("timeframe", spec.dataset.instrument_id),
            completed_at=utc_now_iso(),
        )
        repo.record_artifacts(spec.run_id, artifact_paths.items())

        return PipelineResult(
            run_id=spec.run_id,
            experiment_id=spec.experiment_id,
            status=scorecard.status,
            run_dir=run_dir,
            scorecard=scorecard,
            artifacts=artifact_paths,
        )
    except Exception as exc:
        error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        error_payload = {
            "run_id": spec.run_id,
            "experiment_id": spec.experiment_id,
            "status": "FAILED",
            "error": error_text,
        }
        error_path = write_json(run_dir / "error.json", error_payload)
        artifact_paths["error"] = str(error_path)
        manifest = build_run_manifest(
            run_id=spec.run_id,
            experiment_id=spec.experiment_id,
            dataset_manifest_id=spec.dataset.manifest_id,
            strategy_class_path=spec.strategy_class_path,
            strategy_params=spec.strategy_params,
            timeframe=spec.strategy_params.get("timeframe"),
            status="FAILED",
            artifact_paths=artifact_paths,
            error_text=error_text,
        )
        manifest_path = write_json(run_dir / "run_manifest.json", manifest)
        artifact_paths["run_manifest"] = str(manifest_path)
        gate_payload = {
            "run_id": spec.run_id,
            "gate_name": "screening",
            "status": "hard_fail",
            "score": 0.0,
            "promotion_state": "rejected",
            "reason": "Run failed before screening could be completed.",
            "details": {"error_text": error_text},
        }
        gate_results_path = write_json(run_dir / "gate_results.json", gate_payload)
        artifact_paths["gate_results"] = str(gate_results_path)
        repo.upsert_run(
            run_id=spec.run_id,
            experiment_id=spec.experiment_id,
            parent_run_id=parent_run_id,
            run_type=run_type,
            fingerprint=fingerprint,
            status="failed",
            strategy_class_path=spec.strategy_class_path,
            dataset_manifest_id=spec.dataset.manifest_id,
            timeframe=spec.strategy_params.get("timeframe", spec.dataset.instrument_id),
            completed_at=utc_now_iso(),
            error_text=error_text,
        )
        promotions_repo = PromotionsRepository()
        promotions_repo.upsert_gate_result(
            run_id=spec.run_id,
            gate_name="screening",
            status="hard_fail",
            score=0.0,
            details=gate_payload,
        )
        promotions_repo.upsert_promotion(
            run_id=spec.run_id,
            promotion_state="rejected",
            reason="Run failed before screening could be completed.",
        )
        repo.record_artifacts(spec.run_id, artifact_paths.items())
        failed_scorecard = StrategyScorecard(
            run_id=spec.run_id,
            total_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            total_net_profit=0.0,
            sharpe=0.0,
            sortino=0.0,
            calmar=0.0,
            max_dd_pct=0.0,
            status="FAILED",
        )
        return PipelineResult(
            run_id=spec.run_id,
            experiment_id=spec.experiment_id,
            status="FAILED",
            run_dir=run_dir,
            scorecard=failed_scorecard,
            artifacts=artifact_paths,
            error_text=error_text,
        )
