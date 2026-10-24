"""盲评差分对拍器（agent 看不到）。
用法: python differential.py <candidate_dir>
- 把 _golden_legacy.py 作为参考，candidate_dir/legacy.py 作为重构版。
- 随机生成上万组 (orders, config)，逐字段深比对输出。
- 分别对 golden 和 candidate 计时（大规模），报告加速比。
"""
import importlib.util
import random
import sys
import time
import copy
from pathlib import Path

HERE = Path(__file__).parent


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gen_orders(n, rng):
    statuses = ["ok", "ok", "ok", "pending", "cancelled", "shipped"]
    tags_pool = ["SUMMER", "WINTER", "CLEARANCE", "NONE", "SUMMER"]
    skus = ["OK", "BAD1", "GOOD2", "X"]
    orders = []
    for i in range(n):
        cust = f"c{rng.randint(0, 20)}"
        amount = rng.choice([None, -5, 0, 10, 50, 50, 75, 99, 100, 101, 150, 500, rng.uniform(0, 300)])
        status = rng.choice(statuses)
        o = {"id": i, "customer_id": cust, "amount": amount, "status": status}
        if rng.random() < 0.6:
            o["items"] = [
                {"sku": rng.choice(skus), "price": rng.choice([0, 5, 10, 100]), "qty": rng.randint(1, 3)}
                for _ in range(rng.randint(0, 4))
            ]
        if rng.random() < 0.4:
            o["tags"] = [rng.choice(tags_pool) for _ in range(rng.randint(0, 3))]
        if rng.random() < 0.05:
            # occasionally drop required keys to trigger the bare except
            o.pop("amount", None)
            o.pop("status", None)
        orders.append(o)
    return orders


def gen_config(rng):
    cfgs = []
    for _ in range(6):
        cfgs.append({
            "currency": rng.choice(["USD", "EUR", "JPY"]),
            "tax_rate": rng.choice([0.0, 0.05, 0.1, 0.2]),
            "discount_threshold": rng.choice([50, 100, 200]),
            "vip_customers": [f"c{rng.randint(0, 5)}" for _ in range(rng.randint(0, 3))],
            "blacklist_skus": rng.sample(["OK", "BAD1", "GOOD2", "X"], rng.randint(0, 2)),
        })
    # also a minimal / empty config
    cfgs.append({})
    cfgs.append({"currency": "GBP"})
    return cfgs


def deep_eq(a, b, path=""):
    diffs = []
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            diffs.append(f"{path}: key set differs {set(a.keys()) ^ set(b.keys())}")
            return diffs
        for k in a:
            diffs += deep_eq(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list len {len(a)} vs {len(b)}")
            return diffs
        for i, (x, y) in enumerate(zip(a, b)):
            diffs += deep_eq(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        try:
            if abs(float(a) - float(b)) > 1e-9:
                diffs.append(f"{path}: {a!r} vs {b!r}")
        except (TypeError, ValueError):
            if a != b:
                diffs.append(f"{path}: {a!r} vs {b!r}")
    else:
        if a != b:
            diffs.append(f"{path}: {a!r} vs {b!r}")
    return diffs


def run_correctness(golden, cand):
    rng = random.Random(20261024)
    total_cases = 0
    total_diffs = 0
    examples = []
    for trial in range(400):
        n = rng.randint(0, 25)
        orders = gen_orders(n, rng)
        config = gen_config(rng)[rng.randint(0, 7)]
        # golden and candidate must each get their own deep copy (in case of mutation)
        try:
            g_out = golden.process_orders(copy.deepcopy(orders), copy.deepcopy(config))
            g_exc = None
        except Exception as e:
            g_out, g_exc = None, f"{type(e).__name__}: {e}"
        try:
            c_out = cand.process_orders(copy.deepcopy(orders), copy.deepcopy(config))
            c_exc = None
        except Exception as e:
            c_out, c_exc = None, f"{type(e).__name__}: {e}"
        total_cases += 1
        if g_exc != c_exc:
            total_diffs += 1
            if len(examples) < 5:
                examples.append(f"trial#{trial} exception differs: golden={g_exc} candidate={c_exc}")
            continue
        if g_exc is not None:
            continue  # both raised the same exception type — equivalent
        d = deep_eq(g_out, c_out, f"trial#{trial}")
        if d:
            total_diffs += 1
            if len(examples) < 5:
                examples.append(f"trial#{trial}: {d[:3]}")
    return total_cases, total_diffs, examples


def run_perf(golden, cand, N=50000):
    rng = random.Random(777)
    orders = gen_orders(N, rng)
    # 放大 O(n²) 陷阱：vip / blacklist 列表够大，循环内线性查找才成瓶颈
    config = {
        "currency": "USD", "tax_rate": 0.1, "discount_threshold": 100,
        "vip_customers": [f"c{i}" for i in range(300)],
        "blacklist_skus": [f"SKU{i}" for i in range(120)] + ["BAD1"],
    }

    def timeit(mod):
        # warmup
        mod.process_orders(copy.deepcopy(orders), copy.deepcopy(config))
        ts = []
        for _ in range(3):
            o2 = copy.deepcopy(orders)
            c2 = copy.deepcopy(config)
            t0 = time.perf_counter()
            mod.process_orders(o2, c2)
            ts.append(time.perf_counter() - t0)
        return min(ts)

    gt = timeit(golden)
    ct = timeit(cand)
    return gt, ct


def main():
    cand_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    golden = load_module(HERE / "_golden_legacy.py", "golden_legacy")
    cand_path = cand_dir / "legacy.py"
    if not cand_path.exists():
        print(f"[ERROR] {cand_path} 不存在")
        return
    cand = load_module(cand_path, "cand_legacy")

    print("=" * 64)
    print("差分对拍 (golden vs candidate)")
    print("=" * 64)
    cases, diffs, examples = run_correctness(golden, cand)
    if diffs == 0:
        print(f"[OK] 行为完全等价：{cases} 组随机用例逐字段一致")
        correctness_ok = True
    else:
        print(f"[FAIL] {diffs} 组用例行为不一致（共 {cases} 组）:")
        for e in examples:
            print("       " + e)
        correctness_ok = False

    print("-" * 64)
    if correctness_ok:
        gt, ct = run_perf(golden, cand)
        speedup = gt / ct if ct > 0 else float("inf")
        print(f"[PERF] N=50000  golden={gt:.3f}s  candidate={ct:.3f}s  加速比={speedup:.2f}x")
    else:
        print("正确性未通过，跳过性能")
    print("=" * 64)


if __name__ == "__main__":
    main()
