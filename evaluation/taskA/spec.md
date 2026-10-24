# 任务 A：实现滑动窗口限流器

用 **Python 3** 实现一个滑动窗口速率限制器，写到本目录下的 `solution.py`。

## 要实现的 API

```python
class SlidingWindowLimiter:
    def __init__(self, window_seconds: float, max_calls: int):
        ...

    def allow(self, key: str, ts: float) -> bool:
        """判断 key 在时间戳 ts 的这次调用是否放行。

        规则：考察闭区间 [ts - window_seconds, ts] 内、此前已被放行的调用次数。
        - 若该区间内已放行次数 >= max_calls：本次拒绝，返回 False，且【不记录】本次调用。
        - 否则：本次放行，返回 True，并【记录】本次调用（它会影响后续同 key 的判定）。
        """

    def stats(self) -> dict:
        """返回 {'total': 总调用次数, 'allowed': 放行次数, 'denied': 拒绝次数}。
        total == allowed + denied。每次 allow() 调用都计入 total。"""
```

## 输入约定

- `allow()` 的调用按 **ts 非递减** 的顺序到达（全局单调，跨 key 也是）。
- `ts` 是 float 秒。`window_seconds > 0`，`max_calls >= 1`。
- key 数量可能上千，总调用次数可能上百万。

## 正确性示例

`window_seconds=10, max_calls=2`，同一个 key `"a"`：

| ts | 窗口 [ts-10, ts] 内已放行 | allow 返回 |
|----|----|----|
| 1.0 | 0 | True |
| 5.0 | 1 | True |
| 6.0 | 2 | False（不记录） |
| 12.0 | 只算 ts=5.0（1.0 已过期）→ 1 | True |

## 硬性要求

1. **正确**：判定必须与上面的语义完全一致。
2. **高效**：总调用 N 次时，整体应接近 O(N)，不能随调用次数增长而退化到 O(N²)。内存不能无限增长——过期的记录要被清理掉。
3. `solution.py` 里只放实现，不要写测试/main（评测脚本会 import 它）。可以 `from collections import ...` 等标准库。

## 自测

同目录有 `harness.py`，运行 `python harness.py` 会：小规模对拍一个朴素参考实现验证你的判定正确，再大规模计时。先让它跑通、跑快，再交付。
