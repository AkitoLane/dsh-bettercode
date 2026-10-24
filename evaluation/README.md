# evaluation/ — A/B 评测工具链与产物

本目录让 [EVALUATION.md](../EVALUATION.md) 的每个数字可复现、可审计。

## 结构

```
score_quality.py      AST 代码质量盲评打分器（函数长度/嵌套/圈复杂度/裸except/死代码/魔法数/循环拼接/线性查找/含糊命名）
taskA/                新写任务：滑动窗口限流器（spec + 对拍计时 harness + 参考解 _ref/）
taskB/                重构任务：147 行屎山原题 legacy.py + 特征测试 + 盲评差分对拍器 differential.py
                      （_golden_legacy.py 为行为基准，与 legacy.py 原题相同）
taskC/                审查任务：26 条埋雷清单 _rubric.md + 召回率粗筛器 score_review.py
artifacts/            六个子代理的最终产物（taskX-base = 无 skill，taskX-skill = 带 skill）
```

## 复现

Windows PowerShell，Python 3.12（需 pytest）：

```powershell
# 1. 质量打分（任何候选文件）
python score_quality.py taskB\legacy.py artifacts\taskB-base\legacy.py artifacts\taskB-skill-v1\legacy.py

# 2. 行为等价 + 性能（差分对拍，需把候选 legacy.py 放进一个目录）
python taskB\differential.py <candidate_dir>        # candidate_dir 内含重构后的 legacy.py

# 3. 新写任务对拍计时（solution.py 与 harness.py 同目录）
cd taskA\_ref && python harness.py

# 4. 审查召回率粗筛（需人工复核语义命中）
python taskC\score_review.py artifacts\taskC-skill\review.md
```

注意：差分对拍以 `_golden_legacy.py` 为行为基准；计时数字随机器波动，
比较时应看同一轮内的相对值（golden 基线跨轮波动可达 15%）。
