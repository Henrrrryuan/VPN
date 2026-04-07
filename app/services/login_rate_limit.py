"""登录接口简易限流（按 IP，进程内内存；多 worker 各自计数）。"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

_WINDOW_SEC = 60
_MAX_PER_WINDOW = 15

_attempts: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def is_login_rate_limited(remote_addr: str) -> bool:
    key = (remote_addr or "unknown").strip() or "unknown"
    now = time.monotonic()
    with _lock:
        lst = _attempts[key]
        lst[:] = [t for t in lst if now - t < _WINDOW_SEC]
        if len(lst) >= _MAX_PER_WINDOW:
            return True
        lst.append(now)
    return False
