"""
noteration/logger.py
Central logging hub for the Noteration application.
"""

import logging
import sys
from pathlib import Path

def setup_logging(vault_path: Path | None = None):
    """
    Set up logging to the console and optionally to a file within the vault.
    """
    logger = logging.getLogger("noteration")
    logger.setLevel(logging.DEBUG)
    
    # Avoid duplicate handlers if setup_logging is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler (if vault_path is provided)
    if vault_path:
        log_file = vault_path / ".noteration" / "noteration.log"
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as e:
            print(f"Failed to initialize log file: {e}")

def get_logger(name: str):
    return logging.getLogger(f"noteration.{name}")
