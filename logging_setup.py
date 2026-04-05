from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import AppConfig

SECURITY_LEVEL = 35
logging.addLevelName(SECURITY_LEVEL, "SECURITY")


def security(self: logging.Logger, message: str, *args, **kwargs) -> None:
    if self.isEnabledFor(SECURITY_LEVEL):
        self._log(SECURITY_LEVEL, message, args, **kwargs)


logging.Logger.security = security  # type: ignore[attr-defined]


def configure_logging(config: AppConfig) -> logging.Logger:
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file: Path = config.logs_dir / "bot.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(config.log_level)
    root_logger.handlers.clear()

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    return root_logger
