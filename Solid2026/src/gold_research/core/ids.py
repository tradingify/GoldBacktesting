"""
Utilities for generating unique, deterministic identifiers.

Core to the reproducibility mandate. Features deterministic hash generation
for tracking experiments and mapping them exactly to code/config states.
"""
import hashlib
import json
import time
from datetime import datetime
from typing import Dict, Any

def generate_experiment_id(sprint: str, research_goal: str, instrument: str, family_or_scope: str, batch: str) -> str:
    """
    Generates a deterministic experiment ID based on the naming convention:
    [sprint]__[research_goal]__[instrument]__[family_or_scope]__[date]__[batch]
    
    Args:
        sprint: e.g., 'sprint_01'
        research_goal: e.g., 'baseline_scan'
        instrument: e.g., 'gold'
        family_or_scope: e.g., 'trend'
        batch: e.g., 'a'
        
    Returns:
        Formatted experiment identifier string.
    """
    date_str = datetime.now().strftime("%Y_%m_%d")
    return f"{sprint}__{research_goal}__{instrument}__{family_or_scope}__{date_str}__{batch}"

def generate_run_id(experiment_id: str, strategy_name: str, config_dict: Dict[str, Any]) -> str:
    """
    Generates a unique and deterministic run identifier incorporating:
    - the parent experiment_id
    - strategy_name
    - config dictionary hash state
    - precision timestamp
    
    Args:
        experiment_id: The parent experiment identifier.
        strategy_name: The name of the specific strategy.
        config_dict: The hyper-parameter grid or strategy configuration.
        
    Returns:
        Unique hex-hashed run identifier string.
    """
    timestamp = int(time.time() * 1000)  # milliseconds
    config_json = json.dumps(config_dict, sort_keys=True).encode("utf-8")
    config_hash = hashlib.md5(config_json).hexdigest()[:8]
    return f"{experiment_id}__{strategy_name}__{config_hash}__{timestamp}"


def generate_run_fingerprint(
    *,
    experiment_id: str,
    strategy_class_path: str,
    strategy_params: Dict[str, Any],
    dataset_manifest_id: str,
    instrument_id: str,
    start_time: str | None,
    end_time: str | None,
    cost_profile: str,
    risk_profile: str,
) -> str:
    """Build a stable fingerprint so identical research runs can be deduplicated."""
    payload = {
        "experiment_id": experiment_id,
        "strategy_class_path": strategy_class_path,
        "strategy_params": strategy_params,
        "dataset_manifest_id": dataset_manifest_id,
        "instrument_id": instrument_id,
        "start_time": start_time,
        "end_time": end_time,
        "cost_profile": cost_profile,
        "risk_profile": risk_profile,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.md5(raw).hexdigest()
