"""In-process background job runner (thread pool).

For this workload a thread pool is sufficient; Celery+Redis remains a
documented upgrade path when collection volume outgrows one process.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="audlens-job")
_registry: dict[str, Future] = {}
_lock = threading.Lock()


def submit(key: str, fn, *args, **kwargs) -> str:
    def _wrap():
        with _lock:
            _registry[key] = fut
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("job %s failed", key)
            raise

    with _lock:
        if key in _registry and not _registry[key].done():
            return key
        fut = _executor.submit(_wrap)
        _registry[key] = fut
    return key


def is_running(key: str) -> bool:
    with _lock:
        fut = _registry.get(key)
        return bool(fut and not fut.done())


@dataclass
class JobInfo:
    key: str
    running: bool
