"""
RetailFlow POS - Logging Infrastructure
Structured rotating file logging with separate log categories.
"""
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

from app.config import settings


def setup_logging(log_dir: Optional[Path] = None) -> None:
    """Configure application-wide structured logging.

    Creates rotating file handlers for:
      - application.log (general app events)
      - error.log (ERROR and above)
      - security.log (authentication and authorization events)
      - database.log (database operations)
      - backup.log (backup events)
      - printing.log (printer operations)
    """
    log_dir = log_dir or settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("retailflow")
    root_logger.setLevel(_level_from_str(settings.log_level))

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Application log (INFO and above)
    _add_handler(root_logger, log_dir / "application.log", formatter, logging.INFO)

    # Error log (ERROR and above)
    _add_handler(root_logger, log_dir / "error.log", formatter, logging.ERROR)

    # Security log
    _add_specialized_logger("retailflow.security", log_dir / "security.log", formatter)

    # Database log
    _add_specialized_logger("retailflow.database", log_dir / "database.log", formatter)

    # Backup log
    _add_specialized_logger("retailflow.backup", log_dir / "backup.log", formatter)

    # Printing log
    _add_specialized_logger("retailflow.printing", log_dir / "printing.log", formatter)

    # Suppress noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    root_logger.info(f"Logging initialized. Level={settings.log_level}, dir={log_dir}")


def _add_handler(
    logger: logging.Logger,
    filepath: Path,
    formatter: logging.Formatter,
    level: int,
) -> None:
    """Add a rotating file handler to a logger."""
    handler = logging.handlers.RotatingFileHandler(
        str(filepath),
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _add_specialized_logger(
    name: str,
    filepath: Path,
    formatter: logging.Formatter,
) -> None:
    """Create a specialized logger with its own rotating file handler."""
    logger = logging.getLogger(name)
    logger.setLevel(_level_from_str(settings.log_level))
    logger.propagate = True  # Also pass to root handlers
    handler = logging.handlers.RotatingFileHandler(
        str(filepath),
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _level_from_str(level: str) -> int:
    """Convert a string level name to logging constant."""
    return getattr(logging, level.upper(), logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger by name. Uses the retailflow logger hierarchy."""
    return logging.getLogger(f"retailflow.{name}")