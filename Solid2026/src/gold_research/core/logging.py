"""
Standardized logging configuration for quantitative research.

Ensures that strategy runs, data pipelines, and orchestration
scripts log to the console and to disk with uniform formatting.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

def setup_logger(name: str, log_file: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a structured logger for the research module.
    
    Args:
        name: The name of the logger (e.g., __name__).
        log_file: Optional path to write standard logs to disk.
        level: The minimum logging level to record.
        
    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger
        
    formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    ch.setLevel(level)
    logger.addHandler(ch)
    
    # Optional file handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        fh.setLevel(level)
        logger.addHandler(fh)
        
    return logger

# Provide a root module logger for easy import by submodules
logger = setup_logger("gold_research")
