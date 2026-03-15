"""
Centralized path management for the Gold Research Factory.

This module provides the `ProjectPaths` class, which resolves absolute paths
to all critical directories (data, config, results, reports) based on the
location of the project root.
"""
import os
from pathlib import Path

# Resolve the root directory of the project assuming this file is in src/gold_research/core/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

class ProjectPaths:
    """Provides centralized, absolute paths for all project artifacts."""
    
    ROOT: Path = PROJECT_ROOT
    
    # Base Directories
    CONFIG: Path = ROOT / "config"
    DATA: Path = ROOT / "data"
    SRC: Path = ROOT / "src"
    EXPERIMENTS: Path = ROOT / "experiments"
    RESULTS: Path = ROOT / "results"
    REPORTS: Path = ROOT / "reports"
    JOURNAL: Path = ROOT / "journal"
    DATA_CATALOG: Path = DATA / "catalog"
    
    # Config specific subdirectories
    CONFIG_GLOBAL: Path = CONFIG / "global"
    CONFIG_DATASETS: Path = CONFIG / "datasets"
    CONFIG_EXPERIMENTS: Path = CONFIG / "experiments"
    
    @classmethod
    def get_data_dir(cls) -> Path:
        """Returns the base data directory."""
        return cls.DATA

    @classmethod
    def get_data_raw(cls, source: str = "ib", instrument: str = "gold") -> Path:
        """Returns the path for raw data ingestion, creating it if necessary."""
        path = cls.DATA / "raw" / source / instrument
        path.mkdir(parents=True, exist_ok=True)
        return path
        
    @classmethod
    def get_data_processed_bars(cls, instrument: str = "gold") -> Path:
        """Returns the path for processed Nautilus Bar data, creating it if necessary."""
        path = cls.DATA / "processed" / instrument / "bars"
        path.mkdir(parents=True, exist_ok=True)
        return path
        
    @classmethod
    def get_experiment_config(cls, sprint: str, name: str) -> Path:
        """Returns the path to a specific experiment YAML configuration."""
        return cls.CONFIG_EXPERIMENTS / sprint / f"{name}.yaml"
        
    @classmethod
    def get_result_dir(cls, run_id: str) -> Path:
        """Returns the directory for saving artifacts of a specific run."""
        path = cls.RESULTS / "raw_runs" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path
