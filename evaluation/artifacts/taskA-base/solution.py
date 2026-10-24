"""滑动窗口速率限制器。

设计要点：
- 每个 key 维护一个 collections.deque，存放"已被放行"的调用时间戳。
- 输入约定 ts 全局非递减，因此每个 key 的 deque 天然有序：
  过期清理只需从队首 popleft，每个时间戳至多入队一次、出队一次，
  总复杂度 O(N)（N 为 allow 调用总次数）。
- 窗口是闭区间 [ts - window, ts]：队首时间戳 t 满足 t < ts - window 才算过期；
  t == ts - window 仍计入窗口内（与朴素实现 ts - window <= t <= ts 一致；
  t <= ts 由单调性自动保证）。
- deque 长度恒 <= max_calls（只有窗口内计数 < max_calls 时才记录），
  因此单 key 内存有界，长期运行不会膨胀。
"""

from collections import deque


class SlidingWindowLimiter:
    __slots__ = ("_hist", "_window", "_max", "_total", "_allowed", "_denied")

    def __init__(self, window_seconds: float, max_calls: int):
        self._hist = {}          # key -> deque[float]（升序，长度 <= max_calls）
        self._window = window_seconds
        self._max = max_calls
        self._total = 0
        self._allowed = 0
        self._denied = 0

    def allow(self, key: str, ts: float) -> bool:
        self._total += 1
        hist = self._hist
        dq = hist.get(key)
        if dq is None:
            dq = hist[key] = deque()

        cutoff = ts - self._window
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= self._max:
            self._denied += 1
            return False

        dq.append(ts)
        self._allowed += 1
        return True

    def stats(self) -> dict:
        return {
            "total": self._total,
            "allowed": self._allowed,
            "denied": self._denied,
        }
