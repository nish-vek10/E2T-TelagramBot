# daily_playbook/src/playbook/utils/log.py
from __future__ import annotations

import os
import sys
from loguru import logger


def setup_logger() -> None:
    logger.remove()

    level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    logger.add(
        sys.stdout,
        level=level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
