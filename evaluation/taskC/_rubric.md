# legacy.py 埋雷清单（盲评基准，agent 看不到）

审查报告召回率 = 命中的条目数 / 总条目数。每条给同义词，命中语义即算。

## A 类：结构性坏味道（每条 2 分，共 16 分）

| # | 位置 | 症状 | 关键词 |
|---|---|---|---|
| A1 | process_orders 整个 | 上帝函数：~137 行同时做校验/折扣/VIP/promo/税/字符串拼接/聚合 | 长函数、上帝函数、职责过多、SRP、拆分 |
| A2 | 循环体 | 嵌套 5 层（for→try→if→for→if） | 嵌套过深、guard clause、早返回 |
| A3 | `for i in range(len(orders))` | 索引遍历反模式，应直接迭代 | range(len())、直接迭代、enumerate |
| A4 | 3 处 `skipped = skipped + 1; continue` | 重复代码 | 重复、DRY、提取 |
| A5 | 折扣 if/elif/else | 嵌套条件应提成函数或查表 | 折扣逻辑、嵌套条件、提取函数 |
| A6 | `format_report(data, fancy)` | 布尔陷阱参数 | 布尔陷阱、flag argument、拆函数 |
| A7 | top_customer 手工扫描 | 应 max(items, key=...) | max()、手工扫描 |
| A8 | `if cust in customer_totals.keys(): ... else:` | 应 get/defaultdict | keys()、defaultdict、get |
| A9 | 整个函数无类型注解无 docstring | 缺类型/文档 | 类型注解、docstring |
| A10 | `datetime` 导入未用 | 死导入 | 未用导入、dead import |
| A11 | `if False:` debug 分支 | 死代码 | if False、死代码、删 |
| A12 | 注释掉的 apply_rounding 块 | 注释掉的代码 | 注释代码、删 |
| A13 | `# TODO: clean this up later` | 无主 TODO | TODO |
| A14 | 魔法数 0.1/0.05/0.03/5/3/10 | 具名常量 | 魔法数、magic number、常量 |
| A15 | 魔法字符串 "SUMMER"/"cancelled" 等 | 常量/枚举 | 魔法字符串、枚举、常量 |
| A16 | 单字母变量 c/b/v/t/it、含糊 data | 含糊命名 | 命名、vague、单字母 |

## B 类：错误处理（每条 3 分，共 6 分）

| # | 位置 | 症状 | 关键词 |
|---|---|---|---|
| B1 | `except:` 裸捕获吞一切 | 裸 except、吞异常、KeyboardInterrupt 也被吞 | 裸except、bare except、吞、具体异常 |
| B2 | except 后 continue 静默跳过 | 无日志无上下文，数据悄悄丢失 | 静默、日志、上下文、跳过 |

## C 类：性能（每条 3 分，共 15 分）

| # | 位置 | 症状 | 关键词 |
|---|---|---|---|
| C1 | blacklist 循环内线性查找 | O(n·m·k)，应 set | 黑名单、线性查找、set、O(n²) |
| C2 | vip_customers 循环内线性查找 | O(n·v)，应 set | vip、线性查找、set、O(n²) |
| C3 | `summary = summary + line` 循环拼接 | O(n²) 字符串，应 join/StringBuilder | 字符串拼接、join、O(n²) |
| C4 | blacklist 每单循环内 `config.get` | 循环不变量未外提 | 循环不变量、外提、hoist、每次迭代 |
| C5 | customer_totals.keys() 调用 | keys() 冗余物化视图 | keys()、冗余 |

## D 类：正确性风险（每条 3 分，共 9 分）

| # | 位置 | 症状 | 关键词 |
|---|---|---|---|
| D1 | round 不一致：results 里 round(final)，total_revenue 累加未 round 的 final | 汇总与明细可能对不上（浮点） | round、舍入、不一致、精度 |
| D2 | top_customer 平局时取决于 dict 插入序 | 脆弱语义，并列时无显式规则 | 平局、tie、插入序、确定性 |
| D3 | `amount < 0` 若 amount 是 str 会崩（try 块内会被裸 except 吞掉整单） | 类型健壮性 | 类型、str、健壮 |

## 总分 46。评级：
- ≥40：卓越（接近人工资深审查）
- 30-39：良好
- 20-29：及格
- <20：不足
