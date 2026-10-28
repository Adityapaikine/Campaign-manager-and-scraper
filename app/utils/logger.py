from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.utils.config import LOG_DIR, ensure_directories


def configure_logging() -> logging.Logger:
    ensure_directories()
    logger = logging.getLogger("lead_manager")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = RotatingFileHandler(
        LOG_DIR / "lead_manager.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


logger = configure_logging()
