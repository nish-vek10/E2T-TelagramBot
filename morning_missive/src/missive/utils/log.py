from __future__ import annotations
from loguru import logger

def get_logger(name: str = "missive"):
    return logger.bind(app=name)
