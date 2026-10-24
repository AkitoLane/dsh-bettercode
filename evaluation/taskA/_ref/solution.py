"""参考解：deque 滑动窗口。用于验证 harness 本身正确。"""
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, window_seconds: float, max_calls: int):
        self._window = window_seconds
        self._max = max_calls
        self._hits = {}  # key -> deque of allowed timestamps (non-decreasing)
        self._total = 0
        self._allowed = 0
        self._denied = 0

    def allow(self, key: str, ts: float) -> bool:
        self._total += 1
        dq = self._hits.get(key)
        if dq is None:
            dq = self._hits[key] = deque()
        cutoff = ts - self._window
        # 闭区间 [ts-window, ts]：严格早于 cutoff 的才过期
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self._max:
            self._denied += 1
            return False
        dq.append(ts)
        self._allowed += 1
        return True

    def stats(self) -> dict:
        return {"total": self._total, "allowed": self._allowed, "denied": self._denied}
