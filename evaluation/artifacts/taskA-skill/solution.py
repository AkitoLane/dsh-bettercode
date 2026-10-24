"""精确滑动窗口限流器。

核心结构：dict[key -> deque[已放行调用的时间戳]]。
调用按 ts 全局非递减到达，因此每个 key 的 deque 天然按时间有序：
过期条目只会从队首弹出，新条目只会从队尾追加。每个时间戳至多
入队、出队各一次，故 allow() 摊还 O(1)，N 次调用整体 O(N)；
内存上界 O(活跃 key 数 × max_calls)，过期记录在下次访问时即被清理。
"""
from collections import deque


class SlidingWindowLimiter:
    __slots__ = ("_window_seconds", "_max_calls", "_history",
                 "_allowed_count", "_denied_count")

    def __init__(self, window_seconds: float, max_calls: int):
        self._window_seconds = window_seconds
        self._max_calls = max_calls
        self._history = {}
        self._allowed_count = 0
        self._denied_count = 0

    def allow(self, key: str, ts: float) -> bool:
        history = self._history
        timestamps = history.get(key)
        if timestamps is None:
            timestamps = history[key] = deque()

        # 窗口是闭区间 [ts - window, ts]：恰等于左端点的记录仍有效，只弹严格更小的
        window_start = ts - self._window_seconds
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= self._max_calls:
            self._denied_count += 1
            return False

        timestamps.append(ts)
        self._allowed_count += 1
        return True

    def stats(self) -> dict:
        allowed = self._allowed_count
        denied = self._denied_count
        return {"total": allowed + denied, "allowed": allowed, "denied": denied}
