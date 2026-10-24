"""评测脚手架：正确性对拍 + 性能计时。运行: python harness.py
会 import 同目录的 solution.py 里的 SlidingWindowLimiter。"""
import importlib
import random
import time
import sys


def naive_allow(history, window, max_calls, key, ts):
    """朴素参考实现：每个 key 存全部历史时间戳，每次线性过滤窗口内已放行数。O(n*w)。"""
    h = history.setdefault(key, [])
    cnt = sum(1 for t in h if ts - window <= t <= ts)
    if cnt >= max_calls:
        return False
    h.append(ts)
    return True


def correctness():
    sol = importlib.import_module("solution")
    random.seed(1234)
    keys = ["a", "b", "c", "d", "e"]
    window = 10.0
    max_calls = 3

    # 生成一批非递减时间戳的调用
    calls = []
    ts = 0.0
    for _ in range(3000):
        ts += random.uniform(0.0, 2.0)
        calls.append((random.choice(keys), round(ts, 3)))

    mine = sol.SlidingWindowLimiter(window, max_calls)
    ref_hist = {}
    ref_allowed = ref_denied = 0
    mismatches = []
    for i, (k, t) in enumerate(calls):
        got = mine.allow(k, t)
        exp = naive_allow(ref_hist, window, max_calls, k, t)
        if exp:
            ref_allowed += 1
        else:
            ref_denied += 1
        if got != exp:
            if len(mismatches) < 5:
                mismatches.append((i, k, t, got, exp))

    st = mine.stats()
    ok = True
    if mismatches:
        print(f"[FAIL] 判定与参考实现不一致，{len(mismatches)} 例（前几例）:")
        for m in mismatches:
            print(f"       call#{m[0]} key={m[1]} ts={m[2]} got={m[3]} expected={m[4]}")
        ok = False
    else:
        print("[OK] 判定全部与朴素参考实现一致（3000 次调用）")

    if st.get("total") != len(calls):
        print(f"[FAIL] stats.total={st.get('total')} 应为 {len(calls)}")
        ok = False
    if st.get("allowed") != ref_allowed or st.get("denied") != ref_denied:
        print(f"[FAIL] stats allowed/denied={st.get('allowed')}/{st.get('denied')} 应为 {ref_allowed}/{ref_denied}")
        ok = False
    if ok and st.get("total") == st.get("allowed", -1) + st.get("denied", -2):
        print(f"[OK] stats 自洽: {st}")
    return ok


def perf():
    sol = importlib.import_module("solution")
    N = 400_000
    window = 60.0
    max_calls = 50
    random.seed(99)
    keys = [f"k{i % 2000}" for i in range(N)]
    timestamps = []
    ts = 0.0
    for _ in range(N):
        ts += random.uniform(0.0, 0.05)
        timestamps.append(round(ts, 4))

    limiter = sol.SlidingWindowLimiter(window, max_calls)
    t0 = time.perf_counter()
    for i in range(N):
        limiter.allow(keys[i], timestamps[i])
    dt = time.perf_counter() - t0
    print(f"[PERF] N={N:,} 耗时 {dt:.3f}s  → {N / dt:,.0f} 次/秒")
    return dt


def memory_probe():
    """长时间运行后，过期记录是否被清理：单 key 高频调用，观察是否内存/耗时不随时间膨胀。"""
    sol = importlib.import_module("solution")
    limiter = sol.SlidingWindowLimiter(1.0, 5)
    # 200k 次调用跨越很长时间窗口，若不清理，历史会无限增长
    t0 = time.perf_counter()
    for i in range(200_000):
        limiter.allow("only-key", float(i) * 0.01)  # 每次间隔 0.01s，窗口仅 1s
    dt = time.perf_counter() - t0
    print(f"[MEM] 单 key 20 万次跨长窗口，耗时 {dt:.3f}s（若历史不清理会显著变慢/吃内存）")
    return dt


if __name__ == "__main__":
    print("=" * 60)
    c = correctness()
    print("-" * 60)
    if c:
        perf()
        memory_probe()
    else:
        print("正确性未通过，跳过性能测试")
    print("=" * 60)
