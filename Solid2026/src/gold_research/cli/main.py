"""
Main entry point for the Gold Research Factory CLI.
"""
import argparse
import sys
import logging
import re
from pathlib import Path
from typing import List

# Allow direct CLI execution without requiring a pre-set PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Setup very basic logging for CLI
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("gold_cli")


def _load_experiment_spec(experiment_path: str):
    """Load an experiment YAML into a base spec and raw config payload."""
    from pathlib import Path
    from src.gold_research.core.config import load_yaml
    from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec, DatasetSpec
    from src.gold_research.data.datasets.registry import DatasetRegistry

    exp_path = Path(experiment_path)
    if not exp_path.exists():
        exp_path = Path.cwd() / experiment_path

    raw_yaml = load_yaml(exp_path)
    dataset_manifest_id = raw_yaml["dataset"]["manifest_id"]
    manifest = DatasetRegistry().get_manifest(dataset_manifest_id)
    start_time = raw_yaml["dataset"].get("start_time")
    end_time = raw_yaml["dataset"].get("end_time")
    if start_time is None and manifest:
        start_time = manifest.min_timestamp
    if end_time is None and manifest:
        end_time = manifest.max_timestamp

    strategy_params = raw_yaml["strategy"]["params"]
    if isinstance(strategy_params, dict):
        static_params = {k: v for k, v in strategy_params.items() if not isinstance(v, list)}
    else:
        static_params = {}

    base_spec = ExperimentSpec(
        experiment_id=raw_yaml["experiment"]["id"],
        run_id="base",
        strategy_class_path=raw_yaml["strategy"]["class_path"],
        strategy_params=static_params,
        dataset=DatasetSpec(
            manifest_id=dataset_manifest_id,
            instrument_id=raw_yaml["dataset"]["instrument_id"],
            start_time=start_time,
            end_time=end_time,
        ),
    )

    if "risk" in raw_yaml and isinstance(raw_yaml["risk"], dict):
        profile = raw_yaml["risk"].get("profile") or raw_yaml["risk"].get("profile_name")
        if profile:
            base_spec.risk.profile_name = profile
    if "costs" in raw_yaml and isinstance(raw_yaml["costs"], dict):
        profile = raw_yaml["costs"].get("profile") or raw_yaml["costs"].get("profile_name")
        if profile:
            base_spec.costs.profile_name = profile
    return base_spec, raw_yaml

def cmd_ingest_data(args):
    """Normalize available parquet bars into the processed data area."""
    from pathlib import Path
    from src.gold_research.core.paths import ProjectPaths
    from src.gold_research.data.ingest.ib_loader import load_ib_parquet
    from src.gold_research.data.ingest.normalize import normalize_candles

    source_dir = ProjectPaths.ROOT.parent / "bars"
    if not source_dir.exists():
        raise FileNotFoundError(source_dir)

    processed_dir = ProjectPaths.get_data_processed_bars("gold")
    instrument = args.instrument.lower()
    patterns = ["xauusd_*.parquet"] if instrument in {"gold", "xauusd"} else [f"{instrument}_*.parquet"]
    files = []
    for pattern in patterns:
        files.extend(sorted(source_dir.glob(pattern)))
    if instrument in {"gold", "xauusd"}:
        dxy_file = source_dir / "dxy_1_hour.parquet"
        if dxy_file.exists():
            files.append(dxy_file)

    if not files:
        logger.warning(f"No parquet files found in {source_dir} for instrument {args.instrument}")
        return

    ingested = []
    for parquet_path in files:
        df = load_ib_parquet(parquet_path)
        normalized = normalize_candles(df)
        target_path = processed_dir / parquet_path.name
        normalized.to_parquet(target_path, index=False)
        ingested.append(str(target_path))
    logger.info(f"Ingested {len(ingested)} datasets into {processed_dir}")

def cmd_validate_data(args):
    """Run the quality-report validation flow for a registered dataset."""
    from src.gold_research.core.paths import ProjectPaths
    from src.gold_research.data.datasets.registry import DatasetRegistry
    from src.gold_research.data.validation.quality_report import generate_quality_report
    import pandas as pd

    manifest = DatasetRegistry().get_manifest(args.dataset_id)
    if manifest is None:
        raise FileNotFoundError(f"Dataset manifest not found for {args.dataset_id}")
    if not manifest.source_files:
        raise FileNotFoundError(f"No source files recorded for dataset {args.dataset_id}")

    parquet_path = manifest.source_files[0]["path"]
    df = pd.read_parquet(parquet_path)
    output_path = ProjectPaths.DATA / "checks" / "quality_reports" / f"{args.dataset_id}_report.json"
    passed, report = generate_quality_report(df, args.dataset_id, output_path)
    logger.info(f"Validation {'passed' if passed else 'failed'} for {args.dataset_id}; report at {output_path}")

def cmd_register_dataset(args):
    """Register a processed parquet dataset as a reproducible manifest."""
    from src.gold_research.core.paths import ProjectPaths
    from src.gold_research.data.datasets.manifest import DatasetManifest
    from src.gold_research.data.datasets.registry import DatasetRegistry

    bars_dir = ProjectPaths.get_data_processed_bars("gold")
    parquet_path = bars_dir / f"{args.dataset_id}.parquet"
    if not parquet_path.exists():
        logger.error(f"Could not find processed parquet for dataset '{args.dataset_id}' at {parquet_path}")
        raise FileNotFoundError(parquet_path)

    filename = parquet_path.stem.lower()
    timeframe_match = re.search(r"(1_min|5_mins|15_mins|30_mins|1_hour|4_hours|1_day|gold_m5_2023|m5|1h|4h|15m|5m)", filename)
    timeframe_key = timeframe_match.group(1) if timeframe_match else "unknown"
    timeframe_map = {
        "1_min": "1m",
        "5_mins": "5m",
        "15_mins": "15m",
        "30_mins": "30m",
        "1_hour": "1h",
        "4_hours": "4h",
        "1_day": "1d",
        "gold_m5_2023": "5m",
        "m5": "5m",
        "1h": "1h",
        "4h": "4h",
        "15m": "15m",
        "5m": "5m",
    }
    timeframe = timeframe_map.get(timeframe_key, "unknown")
    instrument = "XAUUSD" if "xauusd" in filename or "gold" in filename else "UNKNOWN"

    manifest = DatasetManifest.create_from_parquet(
        parquet_path=parquet_path,
        dataset_id=args.dataset_id,
        source=args.source,
        instrument=instrument,
        timeframe=timeframe,
        notes=f"Registered from processed parquet: {parquet_path.name}",
    )
    path = DatasetRegistry().register(manifest)
    logger.info(f"Registered dataset manifest at: {path}")

def cmd_run_single(args):
    """Run a single backtest experiment from YAML."""
    logger.info(f"Booting Nautilus Single Runner for {args.experiment}")
    from src.gold_research.backtests.orchestration.run_single import run_single
    from src.gold_research.core.ids import generate_run_id

    base_spec, raw_yaml = _load_experiment_spec(args.experiment)
    spec = base_spec.model_copy(deep=True)
    strategy_name = spec.strategy_class_path.rsplit(".", 1)[-1]
    spec.run_id = generate_run_id(spec.experiment_id, strategy_name, spec.strategy_params)
    
    logger.info(f"Executing Run: {spec.run_id} via Spec...")
    results = run_single(spec)
    logger.info(f"Run completed with status: {results.get('status')}")
    logger.info(f"Artifacts written to: {results.get('run_dir')}")

def cmd_run_grid(args):
    """Run an exhaustive grid search from YAML."""
    logger.info(f"Booting Exhaustive Grid Runner for {args.experiment}")
    from src.gold_research.backtests.specifications.parameter_grid import ParameterGrid
    from src.gold_research.backtests.orchestration.run_grid import run_grid

    base_spec, raw_yaml = _load_experiment_spec(args.experiment)
    grid_params = raw_yaml["strategy"]["params"]
    param_grid = ParameterGrid(grid_params)
    
    logger.info(f"Executing Grid Search for {base_spec.experiment_id}...")
    results = run_grid(base_spec, param_grid, parallel=False)
    logger.info(f"Grid Search completed. Ran {len(results)} permutations.")

def cmd_run_walkforward(args):
    """Run walk-forward validation from an experiment YAML."""
    from src.gold_research.backtests.specifications.parameter_grid import ParameterGrid
    from src.gold_research.backtests.orchestration.run_walkforward import run_walkforward
    from src.gold_research.gates.validation import evaluate_validation
    from src.gold_research.store.promotions_repo import PromotionsRepository

    base_spec, raw_yaml = _load_experiment_spec(args.experiment)
    param_grid = ParameterGrid(raw_yaml["strategy"]["params"])
    result = run_walkforward(base_spec, param_grid)
    summary = result.get("summary", {})
    decision = evaluate_validation(
        {
            "wfo_efficiency": summary.get("wfo_efficiency", 0.0),
            "stress_decay": 1.0,
        }
    )
    PromotionsRepository().upsert_gate_result(
        run_id=base_spec.run_id,
        gate_name=decision.gate_name,
        status=decision.status,
        score=summary.get("wfo_efficiency", 0.0),
        details=decision.details,
    )
    logger.info(f"WFO completed: {summary}")

def cmd_run_stress(args):
    """Run harsh-friction validation for an existing completed run."""
    from pathlib import Path
    from src.gold_research.core.config import load_yaml
    from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
    from src.gold_research.backtests.orchestration.run_stress_suite import run_stress_suite
    from src.gold_research.gates.validation import evaluate_validation
    from src.gold_research.store.promotions_repo import PromotionsRepository
    from src.gold_research.core.paths import ProjectPaths

    run_dir = None
    for exp_dir in (ProjectPaths.RESULTS / "raw_runs").iterdir():
        if exp_dir.is_dir():
            candidate = exp_dir / args.run_id
            if candidate.exists():
                run_dir = candidate
                break
    if run_dir is None:
        raise FileNotFoundError(f"Could not find run directory for {args.run_id}")

    spec_dict = load_yaml(run_dir / "spec.yaml")
    spec = ExperimentSpec(**spec_dict)
    result = run_stress_suite(spec)
    summary = result.get("summary", {})
    decision = evaluate_validation(
        {
            "wfo_efficiency": 1.0,
            "stress_decay": summary.get("stress_decay", 0.0),
        }
    )
    PromotionsRepository().upsert_gate_result(
        run_id=args.run_id,
        gate_name=decision.gate_name,
        status=decision.status,
        score=summary.get("stress_decay", 0.0),
        details=decision.details,
    )
    logger.info(f"Stress suite completed: {summary}")

def cmd_build_strategy_card(args):
    from pathlib import Path
    import json
    from src.gold_research.core.paths import ProjectPaths
    from src.gold_research.reports.strategy_card import StrategyCardReport
    from src.gold_research.analytics.scorecards import StrategyScorecard
    
    logger.info(f"Generating Tear Sheet for run ID {args.run_id}")
    
    raw_runs = ProjectPaths.RESULTS / "raw_runs"
    run_dir = None
    if raw_runs.exists():
        for exp_dir in raw_runs.iterdir():
            if exp_dir.is_dir():
                potential = exp_dir / args.run_id
                if potential.exists():
                    run_dir = potential
                    break
                
    if not run_dir:
        logger.error(f"Run {args.run_id} not found in {raw_runs}.")
        return
        
    with open(run_dir / "scorecard.json", "r") as f:
        scorecard_data = json.load(f)
    scorecard = StrategyScorecard(**scorecard_data)
    
    with open(run_dir / "spec.yaml", "r") as f:
        spec_content = f.read()
        
    md = StrategyCardReport.generate_markdown(scorecard, spec_content, "End-to-end Sprint 00 validation.")
    path = StrategyCardReport.save_report(args.run_id, md)
    logger.info(f"Strategy Card saved to: {path}")

def cmd_build_sprint_report(args):
    logger.info(f"Generating Sprint Summary...")
    from src.gold_research.reports.sprint_report import SprintReport
    from src.gold_research.reports.html_dashboard import HtmlDashboardReport
    report = SprintReport.build_sprint_summary()
    path = SprintReport.save_report(report)
    dashboard = HtmlDashboardReport.build_dashboard()
    logger.info(f"Report Output: {path}")
    logger.info(f"HTML Dashboard Output: {dashboard.get('dashboard_path')}")

def cmd_build_html_dashboard(args):
    logger.info("Generating HTML research dashboard...")
    from src.gold_research.reports.html_dashboard import HtmlDashboardReport

    payload = HtmlDashboardReport.build_dashboard()
    logger.info(f"Dashboard Output: {payload.get('dashboard_path')}")
    logger.info(f"Run detail pages: {payload.get('runs_dir')}")
    logger.info(f"Portfolio pages: {payload.get('portfolios_dir')}")

def main():
    parser = argparse.ArgumentParser(description="Gold Research Factory CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subsystems")
    
    # -- Data Ops --
    p_ingest = subparsers.add_parser("ingest-data", help="Transcribe raw IB CSVs into standardized parquet.")
    p_ingest.add_argument("--instrument", type=str, required=True)
    p_ingest.set_defaults(func=cmd_ingest_data)
    
    p_validate = subparsers.add_parser("validate-data", help="Check integrity of processed data.")
    p_validate.add_argument("--dataset-id", type=str, required=True)
    p_validate.set_defaults(func=cmd_validate_data)
    
    p_register = subparsers.add_parser("register-dataset", help="Add dataset to formal registry.")
    p_register.add_argument("--dataset-id", type=str, required=True)
    p_register.add_argument("--source", type=str, required=True)
    p_register.set_defaults(func=cmd_register_dataset)
    
    # -- Execution Ops --
    p_single = subparsers.add_parser("run-single", help="Execute 1 deterministic configuration.")
    p_single.add_argument("--experiment", type=str, required=True, help="Path to experiment YAML or name.")
    p_single.set_defaults(func=cmd_run_single)
    
    p_grid = subparsers.add_parser("run-grid", help="Exhaustively explore hyperparameter boundaries.")
    p_grid.add_argument("--experiment", type=str, required=True)
    p_grid.set_defaults(func=cmd_run_grid)
    
    p_wfo = subparsers.add_parser("run-walkforward", help="Roll Out-of-Sample testing across time.")
    p_wfo.add_argument("--experiment", type=str, required=True)
    p_wfo.set_defaults(func=cmd_run_walkforward)
    
    p_stress = subparsers.add_parser("run-stress", help="Test friction sensitivity of a winner.")
    p_stress.add_argument("--run-id", type=str, required=True)
    p_stress.set_defaults(func=cmd_run_stress)
    
    # -- Reporting Ops --
    p_card = subparsers.add_parser("build-strategy-card", help="Build markdown tearsheet.")
    p_card.add_argument("--run-id", type=str, required=True)
    p_card.set_defaults(func=cmd_build_strategy_card)
    
    p_sprint = subparsers.add_parser("build-sprint-report", help="Aggregate registry into executive brief.")
    p_sprint.set_defaults(func=cmd_build_sprint_report)

    p_html = subparsers.add_parser("build-html-dashboard", help="Build HTML dashboard for runs and portfolios.")
    p_html.set_defaults(func=cmd_build_html_dashboard)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
        
    args.func(args)

if __name__ == "__main__":
    main()
