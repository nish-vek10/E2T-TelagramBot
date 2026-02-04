# morning_missive/src/missive/utils/retry.py

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_sleep_s: float = 1.0,
    max_sleep_s: float = 6.0,
) -> T:
    last_exc: Exception | None = None

    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if i == attempts:
                break

            # exponential backoff + jitter
            sleep_s = min(max_sleep_s, base_sleep_s * (2 ** (i - 1)))
            sleep_s = sleep_s * (0.7 + random.random() * 0.6)  # ~0.7x..1.3x
            time.sleep(sleep_s)

    assert last_exc is not None
    raise last_exc
