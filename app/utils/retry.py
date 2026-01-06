"""Retry utilities with exponential backoff."""

from __future__ import annotations

import time
import logging
import random
from functools import wraps
from typing import Callable, Iterable, Optional, Type

from app.utils.errors import ScraperError

logger = logging.getLogger(__name__)


def _resolve_attempts(max_attempts: Optional[int], args: tuple) -> int:
    """Determine attempt count, defaulting to instance.retry_attempts when available."""
    if max_attempts is not None:
        return max_attempts
    if args and hasattr(args[0], "retry_attempts"):
        return int(getattr(args[0], "retry_attempts"))
    return 3


def retry_on_error(
    *,
    max_attempts: Optional[int] = None,
    backoff_factor: float = 2.0,
    jitter: float = 0.25,
    max_delay: Optional[float] = None,
    exceptions: Iterable[Type[BaseException]] = (ScraperError,),
    on_retry: Optional[Callable[[BaseException, int, float], None]] = None,
):
    """Retry a callable on specified exceptions with exponential backoff.

    Args:
        max_attempts: Max attempts including the first call. Defaults to the callee's
            ``retry_attempts`` attribute when used on bound methods, otherwise 3.
        backoff_factor: Base for exponential backoff (seconds). Delay grows as factor**(attempt-1).
        jitter: Max random seconds added to each delay to avoid thundering herds.
        max_delay: Optional ceiling for any individual delay.
        exceptions: Exception types that trigger a retry.
        on_retry: Optional callback invoked as ``on_retry(exc, attempt_number, delay_seconds)``.
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = _resolve_attempts(max_attempts, args)
            last_exception: Optional[BaseException] = None

            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except tuple(exceptions) as exc:  # type: ignore[arg-type]
                    last_exception = exc

                    # Honor non-recoverable errors immediately
                    if hasattr(exc, "recoverable") and getattr(exc, "recoverable") is False:
                        raise

                    if attempt >= attempts:
                        raise

                    delay = backoff_factor ** (attempt - 1)
                    if jitter:
                        delay += random.uniform(0, max(jitter, 0))
                    if max_delay is not None:
                        delay = min(delay, max_delay)
                    logger.warning(
                        "Attempt %s/%s failed for %s: %s. Retrying in %.2fs",
                        attempt,
                        attempts,
                        func.__name__,
                        exc,
                        delay,
                    )
                    if on_retry:
                        on_retry(exc, attempt, delay)
                    time.sleep(delay)

            if last_exception:
                raise last_exception

        return wrapper

    return decorator
