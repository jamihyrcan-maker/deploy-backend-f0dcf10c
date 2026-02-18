from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Tuple, Type


@dataclass
class RetryConfig:
    retries: int = 3
    timeout_s: float = 12.0
    backoff_base_s: float = 0.4
    backoff_max_s: float = 4.0
    jitter: bool = True


async def async_retry(
    fn: Callable[[], Awaitable[Any]],
    cfg: RetryConfig,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
) -> Any:
    attempt = 0
    last_exc: Optional[BaseException] = None

    while attempt <= cfg.retries:
        try:
            return await asyncio.wait_for(fn(), timeout=cfg.timeout_s)
        except retry_on as e:
            last_exc = e
            attempt += 1
            if attempt > cfg.retries:
                break

            delay = min(cfg.backoff_max_s, cfg.backoff_base_s * (2 ** (attempt - 1)))
            if cfg.jitter:
                delay *= (0.8 + 0.4 * random.random())  # 0.8x..1.2x
            await asyncio.sleep(delay)

    raise last_exc if last_exc else RuntimeError("async_retry failed")
