"""
Logging setup and management for Unpackr.
"""

import os
import logging
import datetime
import glob
from pathlib import Path


def setup_logging(log_folder: str = 'logs', max_log_files: int = 5) -> Path:
    """
    Set up logging configuration.
    
    Args:
        log_folder: Directory to store log files
        max_log_files: Maximum number of log files to keep
        
    Returns:
        Path to the current log file
    """
    logs_folder = Path(log_folder)
    os.makedirs(logs_folder, exist_ok=True)
    
    # Generate unique log file name
    current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = logs_folder / f'unpackr-{current_time}.log'
    
    # Clean up old log files
    cleanup_old_logs(logs_folder, max_log_files)
    
    # Configure logging
    log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    log_handler = logging.FileHandler(log_file)
    log_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)
    
    return log_file


def cleanup_old_logs(logs_folder: Path, max_files: int):
    """
    Remove old log files, keeping only the most recent ones.
    
    Args:
        logs_folder: Directory containing log files
        max_files: Maximum number of log files to keep
    """
    existing_logs = sorted(glob.glob(str(logs_folder / 'unpackr-*.log')))
    while len(existing_logs) > max_files:
        try:
            os.remove(existing_logs.pop(0))
        except Exception as e:
            logging.warning(f"Could not remove old log file: {e}")


def log_subprocess_error(error, process_name: str):
    """
    Log detailed error information for subprocess failures.
    
    Args:
        error: CalledProcessError exception
        process_name: Name of the process that failed
    """
    import traceback
    
    logging.error(f"{process_name} failed with return code {error.returncode}")
    logging.error(f"Command: {error.cmd}")
    if error.output:
        logging.error(f"Output:\n{error.output}")
    logging.error("Traceback:\n" + traceback.format_exc())
