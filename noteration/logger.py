"""Central logging hub for the Noteration application."""

import logging
import sys
from pathlib import Path


def setup_logging(vault_path: Path | None = None, session_path: Path | None = None) -> None:
    """Set up logging to the console and optionally to a file.

    Logs are sent to the console (INFO level) and optionally to a log file
    within the vault or a specified session directory (DEBUG level).

    Args:
        vault_path: Optional path to the vault for storing logs.
        session_path: Optional path to a session directory for storing logs.

    """
    logger = logging.getLogger("noteration")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler (prioritize session_path)
    log_dir = session_path or vault_path
    if log_dir:
        log_file = log_dir / ".noteration" / "noteration.log"
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except (OSError, IOError) as e:
            print(f"Failed to initialize log file: {e}")


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger for a given module name.

    Args:
        name: The name of the module or component.

    Returns:
        A logging.Logger instance prefixed with 'noteration.'.

    """
    return logging.getLogger(f"noteration.{name}")
