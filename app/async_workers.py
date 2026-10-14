"""Keep CPU worker capacity reserved until canceled callers' threads finish."""
import asyncio
from typing import Callable, TypeVar

Result = TypeVar('Result')


async def run_in_slot(slots: asyncio.Semaphore, fn: Callable[..., Result],
                      *args, **kwargs) -> Result:
    """Propagate cancellation after draining the uncancellable thread worker."""
    async with slots:
        worker = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Repeated cancellation must not release capacity early either.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not worker.cancelled():
                worker.exception()  # Retrieve a worker failure; cancellation wins.
            raise
