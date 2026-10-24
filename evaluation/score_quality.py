"""盲评代码质量打分器（agent 看不到）。用 AST 客观量化 dsh-bettercode 的硬规则。
用法: python score_quality.py <file.py> [file2.py ...]
输出每个文件的指标 + 加权质量分（0-100，越高越好）。"""
import ast
import sys
import io
from pathlib import Path

# 可调阈值，对齐 SKILL.md 的硬规则
MAX_FUNC_LINES = 40
MAX_NESTING = 3
MAGIC_OK = {0, 1, 2, -1, 0.0, 1.0, 0.5}  # 惯用值；业务费率/阈值等其余数字若内联则算魔法


class FuncMetrics(ast.NodeVisitor):
    def __init__(self):
        self.funcs = []  # (name, n_lines, max_nesting, n_params, bool_params, complexity)

    def _nesting(self, node, depth=0):
        """计算函数体内最大嵌套深度（if/for/while/try/with 各加一层）。
        elif 链（If.orelse 恰好是单个 If）视为平级控制流，不加深。"""
        maxd = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith)):
                if (isinstance(child, ast.If) and isinstance(node, ast.If)
                        and len(node.orelse) == 1 and node.orelse[0] is child):
                    maxd = max(maxd, self._nesting(child, depth))  # elif 平级
                else:
                    maxd = max(maxd, self._nesting(child, depth + 1))
            else:
                maxd = max(maxd, self._nesting(child, depth))
        return maxd

    def _complexity(self, node):
        """圈复杂度近似：分支/循环/布尔运算/except/推导式计数 + 1。"""
        c = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With,
                                  ast.AsyncFor, ast.AsyncWith, ast.IfExp, ast.comprehension)):
                c += 1
            elif isinstance(child, ast.BoolOp):
                c += len(child.values) - 1
        return c

    def visit_FunctionDef(self, node):
        self._record(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self._record(node)
        self.generic_visit(node)

    def _record(self, node):
        end = getattr(node, "end_lineno", node.lineno)
        n_lines = end - node.lineno + 1
        nesting = self._nesting(node)
        args = node.args
        all_args = args.args + args.kwonlyargs + args.posonlyargs
        n_params = len(all_args)
        bool_params = sum(
            1 for a in all_args
            if a.annotation is not None and isinstance(a.annotation, ast.Name) and a.annotation.id == "bool"
        )
        complexity = self._complexity(node)
        self.funcs.append((node.name, n_lines, nesting, n_params, bool_params, complexity))


def count_commented_code(src):
    """统计疑似'被注释掉的代码'行数：# 后跟代码样开头，或含真正的赋值语句形态。"""
    import re
    n = 0
    assign_pat = re.compile(r"[A-Za-z_][\w\.]*\s*=[^=]")
    starters = ("if ", "for ", "while ", "print(", "return ", "def ", "import ",
                "else:", "elif ", "try:", "with ")
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("#"):
            body = s.lstrip("#").strip()
            low = body.lower()
            if any(low.startswith(c) for c in starters) or assign_pat.search(body):
                n += 1
    return n


def count_magic_numbers(tree):
    """统计内联在逻辑中的数值字面量。
    排除：白名单惯用值；模块级赋给 UPPER_CASE 具名常量的数字（已具名=已治理）；
    默认参数值（def f(x, rate=0.1) 的参数名即上下文）；字符串键。"""
    named_constant_nodes = set()
    default_nodes = set()
    for node in ast.walk(tree):
        # 模块级 UPPER_CASE 常量赋值：右值里的数字全部豁免
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    for c in ast.walk(node.value):
                        if isinstance(c, ast.Constant):
                            named_constant_nodes.add(id(c))
        # 函数默认参数值豁免
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                for c in ast.walk(d):
                    if isinstance(c, ast.Constant):
                        default_nodes.add(id(c))
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            if node.value in MAGIC_OK:
                continue
            if id(node) in named_constant_nodes or id(node) in default_nodes:
                continue
            n += 1
    return n


def find_bare_except(tree):
    return sum(1 for node in ast.walk(tree)
               if isinstance(node, ast.ExceptHandler) and node.type is None)


def find_if_false(tree):
    """死代码：if False / if 0 恒假分支。"""
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            t = node.test
            if isinstance(t, ast.Constant) and not t.value and t.value is not None:
                n += 1
    return n


def find_loop_string_concat(tree):
    """AST 精确检测：循环体内对 str 类型目标做 s = s + ... / s += ...（字符串拼接 O(n²) 嫌疑）。
    只看 BinOp(Add) 且左操作数是被累加的同一 Name。数值累加无法从 AST 判型，
    故要求上下文有字符串信号（str() 调用、字符串常量、变量名含 str/summary/line/text/out）。"""
    str_hints = ("str", "summary", "line", "text", "out", "msg", "message", "report", "s_", "_s")
    n = 0
    for loop in ast.walk(tree):
        if not isinstance(loop, (ast.For, ast.While)):
            continue
        for node in ast.walk(loop):
            target = None
            if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add) \
               and isinstance(node.target, ast.Name) and isinstance(node.value, ast.BinOp) \
               and isinstance(node.value.op, ast.Add):
                target = node.target.id
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
               and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.BinOp) \
               and isinstance(node.value.op, ast.Add) \
               and isinstance(node.value.left, ast.Name) \
               and node.value.left.id == node.targets[0].id:
                target = node.targets[0].id
            if target:
                lname = target.lower()
                body_src = ast.unparse(node)
                if any(h in lname for h in str_hints) or "str(" in body_src or '"' in body_src or "'" in body_src:
                    n += 1
    return n


def find_linear_search_in_loop(tree):
    """for 循环体内出现 `for x in list` 且做 == 比较（线性查找嫌疑）。粗略：嵌套 for + Compare。"""
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            for inner in ast.walk(node):
                if inner is not node and isinstance(inner, ast.For):
                    has_cmp = any(isinstance(c, ast.Compare) for c in ast.walk(inner))
                    if has_cmp:
                        n += 1
                    break
    return n


def find_vague_names(tree):
    vague = {"data", "info", "temp", "tmp", "flag", "obj", "val", "value", "x", "y", "foo",
             "bar", "res", "result", "d", "a", "b", "item", "thing", "stuff"}
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            if node.name.lower() in {"do_something", "handle", "process", "run", "do", "func", "do_it"}:
                names.add(node.name)
        if isinstance(node, ast.Name) and node.id.lower() in vague:
            names.add(node.id)
    return names


def score_file(path):
    src = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src)

    fm = FuncMetrics()
    fm.visit(tree)

    total_lines = len(src.splitlines())
    n_funcs = len(fm.funcs)
    max_func_lines = max((f[1] for f in fm.funcs), default=0)
    max_nesting = max((f[2] for f in fm.funcs), default=0)
    max_complexity = max((f[5] for f in fm.funcs), default=0)
    long_funcs = sum(1 for f in fm.funcs if f[1] > MAX_FUNC_LINES)
    deep_funcs = sum(1 for f in fm.funcs if f[2] > MAX_NESTING)
    commented_code = count_commented_code(src)
    magic = count_magic_numbers(tree)
    bare_except = find_bare_except(tree)
    if_false = find_if_false(tree)
    loop_concat = find_loop_string_concat(tree)
    linear_in_loop = find_linear_search_in_loop(tree)
    vague = find_vague_names(tree)

    # 加权扣分（从 100 起扣）
    score = 100.0
    penalties = []

    def penalize(amount, label):
        nonlocal score
        if amount > 0:
            score -= amount
            penalties.append(f"-{amount:.0f} {label}")

    penalize(long_funcs * 8, f"过长函数(>{MAX_FUNC_LINES}行) x{long_funcs}")
    penalize(deep_funcs * 5, f"嵌套>{MAX_NESTING}层 x{deep_funcs}")
    penalize(max(0, max_complexity - 15) * 1.5, f"高圈复杂度(max={max_complexity})")
    penalize(commented_code * 3, f"注释掉的代码 x{commented_code}")
    penalize(if_false * 6, f"if False 死代码 x{if_false}")
    penalize(bare_except * 6, f"裸 except x{bare_except}")
    penalize(min(magic, 15) * 1.5, f"魔法数 x{magic}")
    penalize(loop_concat * 3, f"循环内字符串拼接嫌疑 x{loop_concat}")
    penalize(linear_in_loop * 6, f"循环内线性查找嫌疑 x{linear_in_loop}")
    penalize(len(vague) * 1.5, f"含糊命名 x{len(vague)}")

    score = max(0.0, score)

    return {
        "file": str(path),
        "total_lines": total_lines,
        "n_funcs": n_funcs,
        "max_func_lines": max_func_lines,
        "max_nesting": max_nesting,
        "max_complexity": max_complexity,
        "long_funcs": long_funcs,
        "deep_funcs": deep_funcs,
        "commented_code": commented_code,
        "magic_numbers": magic,
        "bare_except": bare_except,
        "if_false": if_false,
        "loop_concat": loop_concat,
        "linear_in_loop": linear_in_loop,
        "vague_names": sorted(vague),
        "score": round(score, 1),
        "penalties": penalties,
    }


def main():
    results = [score_file(p) for p in sys.argv[1:]]
    for r in results:
        print("=" * 60)
        print(f"文件: {r['file']}")
        print(f"  质量分: {r['score']}/100")
        print(f"  总行数={r['total_lines']} 函数数={r['n_funcs']} "
              f"最长函数={r['max_func_lines']}行 最深嵌套={r['max_nesting']} 最大圈复杂度={r['max_complexity']}")
        print(f"  过长函数={r['long_funcs']} 深嵌套函数={r['deep_funcs']} 裸except={r['bare_except']} "
              f"if-False={r['if_false']} 魔法数={r['magic_numbers']} 注释代码={r['commented_code']}")
        print(f"  循环拼接嫌疑={r['loop_concat']} 循环线性查找嫌疑={r['linear_in_loop']}")
        if r["vague_names"]:
            print(f"  含糊命名: {', '.join(r['vague_names'])}")
        if r["penalties"]:
            print("  扣分项: " + "; ".join(r["penalties"]))
    if results:
        print("=" * 60)
        print("汇总: " + "  ".join(f"{Path(r['file']).parent.name}/{Path(r['file']).name}={r['score']}" for r in results))


if __name__ == "__main__":
    main()
