from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from .errors import MediaComponentError, provider_error_code


T = TypeVar("T")


async def execute_with_retries(
    component: str,
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    timeout_seconds: float,
) -> T:
    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except Exception as error:
            last_error = error
    assert last_error is not None
    raise MediaComponentError(
        provider_error_code(component, last_error),
        str(last_error),
    ) from last_error
