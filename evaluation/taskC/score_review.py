"""审查报告召回率辅助打分（agent 看不到）。
用法: python score_review.py <review.md>
对 _rubric.md 里 27 条埋雷逐条做关键词粗匹配，输出命中矩阵。
粗匹配仅作线索，最终判定由人工复核 review.md 原文。"""
import re
import sys
from pathlib import Path

# (id, 分值, 匹配正则组 —— 任一命中即算疑似命中)
RUBRIC = [
    ("A1", 2, r"长函数|过长|上帝函数|god|职责过多|单一职责|SRP|拆分.*函数|函数.*拆分|90\s*行|137\s*行|太长"),
    ("A2", 2, r"嵌套(过深|太深|层级)|nesting|guard\s*clause|卫语句|早返回|early\s*return|缩进.*层|5\s*层"),
    ("A3", 2, r"range\s*\(\s*len|索引遍历|直接迭代|for\s+order\s+in|enumerate"),
    ("A4", 2, r"重复代码|duplicat|DRY|skipped\s*=\s*skipped|三处.*continue|重复.*skipped|提取.*skip"),
    ("A5", 2, r"折扣.*(提取|函数|查表|嵌套)|discount.*(extract|nested)|嵌套条件"),
    ("A6", 2, r"布尔陷阱|boolean\s*trap|flag\s*argument|fancy.*(拆|参数|布尔)|布尔参数"),
    ("A7", 2, r"top_customer.*(max|扫描|遍历)|max\s*\(.*key|手工扫描"),
    ("A8", 2, r"\.keys\(\)|defaultdict|customer_totals.*(get|defaultdict)|键.*检查"),
    ("A9", 2, r"类型注解|type\s*hint|docstring|类型标注|无文档"),
    ("A10", 2, r"datetime.*(未|没有|不用|unused)|未用.*导入|dead\s*import|无用导入|import\s*datetime"),
    ("A11", 2, r"if\s+False|死代码|dead\s*code|debug.*分支|永不.*(执行|运行)|不可达"),
    ("A12", 2, r"注释掉|注释.*(代码|块)|apply_rounding|commented.*(out|code)"),
    ("A13", 2, r"TODO"),
    ("A14", 2, r"魔法数|magic\s*number|0\.1|0\.05|0\.03|具名常量|命名常量|硬编码.*(数|值)"),
    ("A15", 2, r"魔法字符串|magic\s*string|SUMMER.*常量|字符串常量|枚举.*(状态|标签)|status.*枚举"),
    ("A16", 2, r"含糊命名|vague|单字母|命名.*(不清|差|含糊)|\bdata\b.*命名|c\b.*b\b.*v\b|变量名"),
    ("B1", 3, r"裸\s*except|bare\s*except|except\s*:|吞.*(异常|错误)|KeyboardInterrupt|SystemExit|捕获.*过宽|宽泛.*捕获"),
    ("B2", 3, r"静默|悄悄|无日志|没有日志|不记录|丢失.*(数据|信息)|异常.*(上下文|信息)"),
    ("C1", 3, r"黑名单|blacklist.*(线性|set|集合|查找)|blocked.*循环|O\(n.*m|O\(n²\)|O\(n\^2\)"),
    ("C2", 3, r"vip.*(线性|set|集合|查找|遍历)|is_vip.*循环"),
    ("C3", 3, r"字符串拼接|summary.*(拼接|\+|join)|join|O\(n²\).*字符串|不可变.*拼接|StringBuilder"),
    ("C4", 3, r"循环不变|外提|hoist|每(次|单).*(config|get)|config\.get.*(循环|内)|重复.*config"),
    ("C5", 3, r"\.keys\(\).*(冗余|多余|没必要|删)|keys\(\).*视图|不需要.*keys"),
    ("D1", 3, r"round.*(不一致|不匹配|精度)|舍入.*(不一致|误差)|汇总.*(明细|不一致)|total_revenue.*(round|舍入|精度)|浮点.*(累加|误差)"),
    ("D2", 3, r"平局|tie|并列|插入序|dict.*顺序|确定性|top_customer.*(顺序|规则|并列)"),
    ("D3", 3, r"类型.*(健壮|安全|崩)|str.*(比较|崩|<)|amount.*(类型|str|字符串)|TypeError"),
]


def main():
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    hit, miss, score, total = [], [], 0.0, 0.0
    for rid, pts, pat in RUBRIC:
        total += pts
        if re.search(pat, text, re.IGNORECASE):
            hit.append(rid)
            score += pts
        else:
            miss.append(rid)
    print(f"文件: {path}")
    print(f"疑似命中 {len(hit)}/{len(RUBRIC)} 条，粗分 {score:.0f}/{total:.0f}")
    print(f"命中: {', '.join(hit)}")
    print(f"未中: {', '.join(miss) if miss else '无'}")


if __name__ == "__main__":
    main()
