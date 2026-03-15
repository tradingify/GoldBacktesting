"""
Configuration parsing for the research environment.

Manages loading and saving global settings, dataset manifests,
cost profiles, and overarching YAML files.
"""
import yaml
from pathlib import Path
from typing import Dict, Any

def load_yaml(path: Path) -> Dict[str, Any]:
    """
    Loads a YAML configuration file into a dictionary.
    
    Args:
        path: Pathlib object pointing to the target YAML file.
        
    Returns:
        A dictionary representation of the YAML.
        
    Raises:
        FileNotFoundError: If the config path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data if data is not None else {}

def save_yaml(data: Dict[str, Any], path: Path) -> None:
    """
    Saves a given dictionary to a YAML configuration file.
    
    Args:
        data: The dictionary to save.
        path: The target filepath to write the YAML onto.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
