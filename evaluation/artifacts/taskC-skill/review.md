# legacy.py 代码审查报告

审查对象：`legacy.py`（147 行，`process_orders` + `format_report`）
审查方法：依据 `dsh-bettercode` skill 及其 `references/code-smells.md`、`references/performance-patterns.md` 逐条排查。
总体结论：**该函数是一个约 136 行的"上帝函数"，同时犯下三类致命问题 —— 金钱用 float 计算（对账事故）、三处隐藏的 O(n²)/O(n·m) 复杂度（规模事故）、裸 except 吞错且校验漏洞导致未捕获崩溃（静默数据丢失 + 中途崩停）。** 数据规模一旦到 10⁴~10⁵ 单，性能与正确性问题都会显性化。

统计：**坏味道 24 条，性能问题 9 条，风险点 16 条**。各节内按严重程度排序（🔴 高 / 🟠 中 / 🟡 低）。

复杂度约定：N = 订单数，I = 每单条目数，B = 黑名单 SKU 数，V = VIP 客户数，T = 每单标签数，S = summary 总长度。

---

## 一、坏味道清单（24 条）

### 🔴 高严重度

**S1. Long Function / 上帝函数 — L4-140 `process_orders`**
- 症状：约 136 行，远超 40 行上限；同时负责配置解析、字段提取、校验、条目计价、折扣、VIP、促销、税、聚合、字符串报告、Top 客户查找，需要用十几个"然后"复述。
- 病因：职责不断追加，没人愿意拆（原作者 2023 年离职，见 L5 TODO）。
- 处方：Extract Method —— 每段注释就是一个新函数的名字：`extract_order_fields`、`compute_item_subtotal(items, blacklist)`、`compute_discount(amount, threshold)`、`compute_vip_discount`、`compute_promo(tags)`、`build_summary_line`、`find_top_customer`。主函数应读起来像一张计价流程清单。

**S2. Mixed Abstraction Levels（抽象层级混杂）— L4-140**
- 症状：高层策略（"计算折扣""处理 VIP"）与低层细节（`summary = summary + "order " + str(oid) + ...`、逐 key 提取）混在同一函数体。
- 病因：细节没有下沉。
- 处方：随 S1 拆分，让主函数只剩一层策略语句。

**S3. Swallowed Error（被吞的错误）— L31-33 裸 `except:`**
- 症状：`except:` 不带异常类型、不记录日志、不带任何定位上下文（哪个订单、什么错误），只 `skipped + 1`。数据损坏与格式不符被静默归入同一个计数。
- 病因："让报错消失最快"。
- 处方：每个 catch 三选一（恢复 / 加上下文重抛 / 记录后终止）。这里应改为显式校验（见 S4），确需捕获时只捕 `KeyError`/`TypeError`，用 logging 记录订单原始内容与异常，`skipped` 按原因分类计数。

**S4. Exception as Control Flow（异常当控制流）— L24-33**
- 症状：用 try/except 处理"字段可能缺失"这种可预期失败；且 try 块内混用必填字段（`order["id"]`）与可选字段（`order.get("items", [])`），职责纠缠。
- 病因：没设计错误通道，把提取和校验塞进同一个 try。
- 处方：可预期失败用显式判断：`if not isinstance(order, dict) or "id" not in order: skip(reason)`；或抽一个 `parse_order(order) -> Order | None` 的校验函数，一次校验、处处安全。

**S5. Dead Code（死代码）— L117-119 `if False:` 块**
- 症状：永假分支 + "legacy debug path, never runs" 注释，代码自己承认永远不执行。
- 病因：不敢删。
- 处方：删。版本控制记得一切。需要调试路径就用 `logging.debug` + 日志级别控制。

**S6. Dead Code（注释掉的代码块）— L18-20**
- 症状：`# old logic: apply_rounding = ...` 三行被注释的旧实现。
- 病因：注释保留代替删除。
- 处方：删。需要历史查 git。特别注意：它暗示"舍入曾是可配置的"，若该行为仍被下游依赖，这是一个未交代的契约变更（见 R1/R2），删除前应确认。

**S7. Dead Code（未使用的 import）— L1 `import datetime`**
- 症状：`datetime` 全文件从未使用。
- 病因：历史残留。
- 处方：删。

**S8. Primitive Obsession（基本类型偏执）— 全文件**
- 症状：金额用 `float`（L90-92）、订单状态用裸字符串 `"cancelled"`/`"pending"`（L38-41）、订单/配置/结果全用裸 dict 传来传去，无任何类型或校验。
- 病因：不想建类型。
- 处方：金额用 `Decimal` 或整数分；状态用 `enum.Enum`；订单建 `dataclass Order`（校验放进构造函数）；配置建 `dataclass PricingConfig`。

### 🟠 中严重度

**S9. Magic Number（魔法值）— L62-88 等多处**
- 症状：`0.1`（折扣率，L63）、`0.05`（L66）、`discount_threshold / 2`（L65）、`0.03`（VIP 折扣率，L77）、`5/3/10`（促销减免，L84-88）、默认 `0.1`（税率，L13）、默认 `100`（阈值，L14）散落各处。尤其 `0.1` 既是默认税率又是折扣率，两个不同业务含义共用一个裸数字，极易改错。
- 病因：写的时候图快。
- 处方：具名常量集中定义：`TIER1_DISCOUNT_RATE = 0.10`、`TIER2_DISCOUNT_RATE = 0.05`、`VIP_DISCOUNT_RATE = 0.03`、`PROMO_AMOUNTS = {...}`；更好的做法是全部进 config 并给默认值表。

**S10. Magic String（魔法字符串）— L38/41/83-87**
- 症状：`"cancelled"`、`"pending"`、`"SUMMER"`、`"WINTER"`、`"CLEARANCE"`、`"USD"` 直接内联比较。
- 病因：没有枚举/常量层。
- 处方：状态用 `OrderStatus` 枚举；标签用常量或 promo 表的 key（见 S13）。

**S11. Boolean Trap（布尔陷阱）— L143-147 `format_report(data, fancy)`**
- 症状：`fancy` 布尔参数分叉出两套完全不同的输出格式；调用处 `format_report(d, True)` 不可读。
- 病因：用参数省了一次拆分。
- 处方：拆成 `format_report_plain(data)` 与 `format_report_fancy(data)` 两个语义函数；或传枚举 `ReportStyle.PLAIN/FANCY`。

**S12. Mysterious Name（含糊命名）— 多处**
- 症状：`data`（L143，是什么 data？）、`fancy`（L143）、`it`（L48）、`b`（L54）、`v`（L72）、`t`（L82）、`oid`/`cust`（L25-26）、`line`（L95）。
- 病因：起名时没想清楚它是什么，缩写图快。
- 处方：`report_data`、`item`、`blocked_sku`、`vip_id`、`tag`、`order_id`、`customer_id`、`summary_line`。好名字让一半注释（如 L52 "is this sku blacklisted?"）变得多余。

**S13. if/elif 硬编码分支应为数据表 — L82-88**
- 症状：促销规则写成 if/elif 链，新增一个标签要改代码。
- 病因：规则与代码没有分离。
- 处方：模块级常量 `PROMO_AMOUNTS = {"SUMMER": 5, "WINTER": 3, "CLEARANCE": 10}`，循环体变成 `promo += PROMO_AMOUNTS.get(tag, 0)`；规则可配置化后进 config。

**S14. 冗余 else 分支（准死代码）— L64-68**
- 症状：`discount = 0` 已在 L61 初始化，L67-68 的 `else: discount = 0` 是重复赋值；整段嵌套 if/else 可平铺。
- 病因：防御式复制粘贴。
- 处方：早返回/平铺：`if amount > threshold: rate = TIER1 elif amount > threshold/2: rate = TIER2 else: rate = 0`，或直接查档位表。

**S15. 冗余的 dict 聚合模式 — L99-102**
- 症状：`if cust in customer_totals.keys(): ... else: ...` 手写"存在则累加否则初始化"，还多调一次 `.keys()`。
- 病因：不熟悉惯用法。
- 处方：`customer_totals[cust] = customer_totals.get(cust, 0) + final` 或 `collections.defaultdict(float)`。

**S16. 非惯用索引循环 — L22-23**
- 症状：`for i in range(len(orders)): order = orders[i]`，`i` 除索引外无用途。
- 病因：从 C 系语言带来的习惯。
- 处方：`for order in orders:`。顺带解除对 `len()` 的依赖（见 R16）。

**S17. `== None` / `== True` 比较 — L35、L76**
- 症状：`amount == None`、`is_vip == True`，违反 PEP 8，且 `==` 可被重载改变语义。
- 病因：不了解单例比较语义。
- 处方：`amount is None`、`if is_vip:`。

**S18. 手工 `str()` 拼接代替 f-string — L95**
- 症状：五段 `+` 拼接构造摘要行，难读易错。
- 病因：旧式写法。
- 处方：`f"order {oid} cust {cust} final {round(final, 2)} {currency};"`（配合 P3 收集进 list）。

**S19. 手写 max 扫描 — L122-127**
- 症状：手工维护 `top_customer/top_value` 找最大值。
- 病因：未用标准库。
- 处方：`top_customer = max(customer_totals, key=customer_totals.get, default=None)`。一行替代六行，且消除 `-1` 哨兵（见 R6）。

### 🟡 低严重度

**S20. 未交代的 TODO — L5**
- 症状：`# TODO: clean this up later - original author left 2023`，无负责人、无追踪号、已过期两年多。
- 病因：把重构意愿当注释存起来。
- 处方：转为工单（本次审查即可作为该工单的依据），代码里删除。

**S21. 注释与代码矛盾 — L121**
- 症状：`# find top customer by scanning repeatedly`，但代码只扫一遍，并无 "repeatedly"。
- 病因：注释描述的是被废弃的旧实现。
- 处方：过期注释是 bug。改代码后（S19）连注释一起删。

**S22. 缺 docstring / 类型注解 / 测试 — 全文件**
- 症状：`process_orders` 的输入契约（orders 是什么形状？amount 含不含条目价？）、输出契约、边界行为（空列表返回什么？——实际返回全零 + `top_customer: None`）均无文档；无任何测试。
- 病因：遗留代码无人补。
- 处方：重构前先补一组特征测试（characterization tests）锁住当前行为，再动刀；补类型注解 `def process_orders(orders: list[dict], config: dict) -> dict`。

**S23. `skipped` 混合计数，可观测性缺失 — L32/36/39/42**
- 症状：字段缺失、amount 为 None、已取消、pending 负额四种完全不同的原因共用一个计数器；"数据质量事故"与"正常业务过滤"在报表上不可区分。
- 病因：图省事。
- 处方：按原因分类：`skipped = {"malformed": 0, "no_amount": 0, "cancelled": 0, "negative_pending": 0}`，并对 malformed 记日志。

**S24. 必填/可选字段访问风格不一致 — L25-30**
- 症状：同一 try 块里 `order["id"]`（缺失即异常）与 `order.get("items", [])`（缺失给默认）混用，读者无法一眼判断哪些字段是契约必需的。
- 病因：字段重要性没有显式表达。
- 处方：随 S4/S8 的 `parse_order`/`Order` dataclass 一并解决：必填字段显式校验，可选字段给默认值。

---

## 二、性能问题清单（9 条，含复杂度分析）

当前最坏总复杂度：**O(N·(I·B + V·1) + S²)** —— 三处设计期就该做对的宏观性能错误。以下按严重度排序。

**P1. 🔴 循环内黑名单线性扫描 — L54-56**
```python
for b in blacklist:
    if b == sku:
        blocked = True
```
- 每个条目对黑名单做 O(B) 全表扫描，总计 **O(N·I·B)**。这是 performance-patterns 反模式表第一条："循环内 `list.contains(x)`"。
- 退化：N=10⁵ 单、I=10 条目、B=10³ SKU → 10⁹ 次比较，分钟级耗时；B 增长时线性恶化。
- 处方：循环外建 `blacklist_set = set(config.get("blacklist_skus", ()))`，判断 `sku in blacklist_set`，O(B)→O(1)，总复杂度降为 O(N·I)。

**P2. 🔴 循环内 VIP 线性扫描 — L72-74**
```python
for v in vip_customers:
    if v == cust:
        is_vip = True
```
- 每单对 VIP 列表 O(V) 扫描，总计 **O(N·V)**。VIP 名单是典型的"成员判断"场景，数据结构选择表明确写着：Set，绝不遍历 List。
- 退化：VIP 计划扩张到 10⁴ 人、日订单 10⁵ → 10⁹ 次比较。
- 处方：循环外 `vip_set = set(vip_customers)`，`is_vip = cust in vip_set`，降为 O(N)。

**P3. 🔴 字符串循环 `+=` 拼接 summary — L95-96**
```python
summary = summary + line
```
- Python 字符串不可变，每次 `+=` 都整体复制，总计 **O(S²)**（S 为 summary 最终长度）。performance-patterns §4："字符串循环 += 是 O(n²) —— 一律 join / builder"。
- 退化：每行约 50 字符，N=10⁵ → S≈5MB，累计复制约 S²/2 ≈ 1.2×10¹³ 字节，实际表现为运行时间随订单数平方增长、内存带宽打满。
- 处方：`lines.append(f"order {oid} ...")`，循环外 `summary = "".join(lines)`，总量 O(S)。

**P4. 🟠 两处成员扫描命中后不 break — L54-56、L72-74**
- 症状：找到匹配后仍继续扫完整个列表（`blocked`/`is_vip` 只会被重复置 True）。
- 影响：平均多扫约一半列表；在 P1/P2 的 O(n·m) 基础上再乘常数。
- 处方：改 Set 后自然消失；若暂不改结构，至少 `break`。

**P5. 🟠 循环不变量未提出：`config.get("blacklist_skus", [])` 在订单循环内 — L47**
- 症状：每个订单都重新读一次 config；键缺失时每次调用还**新建一个默认空列表**（N 次无谓分配）。
- 处方：与 P1 一并提到循环外（且只建一次 set）。热路径清单第一条："循环不变量全部提到循环外"。

**P6. 🟡 `discount_threshold / 2` 每单重算 — L65**
- 症状：循环不变的除法每单算一次。单次开销微不足道，但违反热路径仪式，且掩盖了"半阈值"这个业务概念。
- 处方：循环外 `half_threshold = discount_threshold / 2` 并具名（如 `TIER2_THRESHOLD`）。

**P7. 🟡 `customer_totals` 双次哈希查找 — L99-102**
- 症状：`in keys()` 判断一次、下标读一次、下标写一次，共三次哈希操作。
- 澄清（避免误报）：Python 3 中 `dict.keys()` 是视图，`in` 为 O(1)，**这不是 O(n²)**，只是常数因子浪费 + 不符合惯用法。
- 处方：`customer_totals[cust] = customer_totals.get(cust, 0) + final`（一次查找）或 `defaultdict`。

**P8. 🟡 `range(len(orders))` 索引迭代 — L22-23**
- 症状：每轮多做一次下标寻址，比直接迭代慢（常数因子，CPython 约 10-20%）。
- 处方：`for order in orders:`（同 S16）。

**P9. 🟡 全量物化内存 O(N) — L104-112、L95-96**
- 症状：`results` 列表 + `summary` 大字符串 + `customer_totals` 同时驻留内存，峰值内存随 N 线性增长且有三份。
- 退化：N=10⁶ 时 results 约数百 MB；若 summary 按 P3 修复后仍达数十 MB。
- 处方：若调用方是流式消费（写文件/发响应），改生成器 `yield` 逐单产出；聚合量（totals/top_customer）单独一趟或边产边聚。当前契约要求一次性返回 dict，此条为规模上界预警而非必改项。

---

## 三、风险点（16 条，生产 bug 排查）

**R1. 🔴 金钱用 float 计算 + `round()` 银行家舍入 — L90-92、L107-109、L132-136**
- float 二进制表示无法精确表达多数十进制小数（`0.1 + 0.2 != 0.3`）；Python `round()` 是 round-half-to-even：`round(2.675, 2) == 2.67`、`round(0.125, 2) == 0.12`。财务场景期望的通常是 half-up，**每单可能差 1 分钱，百万单累计成真实资损/对账差异**。
- 处方：`Decimal`（并显式 `quantize(ROUND_HALF_UP)`）或全程整数分；舍入策略写成具名常量与文档。

**R2. 🔴 逐单舍入值与总额不自洽 — L109 vs L114、L132-133**
- `results` 里的 `final` 是 `round(final, 2)`，而 `total_revenue` 累加的是**未舍入**的 `final`。下游若把明细求和对总账，会得到与 `total_revenue` 相差若干分的结果——审计/对账必然报警。`tax` 同理（`round(subtotal)+round(tax) != round(final)` 可差 0.01）。
- 处方：定义单一舍入点（要么全用未舍入值计算、最后统一舍入；要么逐单舍入后累加舍入值），并在契约中写明。

**R3. 🔴 裸 `except:` 吞掉一切，包括 `KeyboardInterrupt`/`SystemExit` — L31-33**
- 裸 except 连 Ctrl-C、进程退出信号都拦截并计入 skipped；真实的结构损坏（order 不是 dict、amount 是字符串）被静默吞掉，**数据无声丢失且无法定位是哪一单**。
- 处方：只捕具体异常（`KeyError`、`TypeError`），记录订单定位信息；或改显式校验（S4）。

**R4. 🔴 非数值 `amount` 导致 try 块之外未捕获崩溃 — L27 → L62**
- 校验只挡 `amount == None`（L35）。若 `amount` 是字符串（上游 JSON 常见 `"100.00"`），L41 `amount < 0`（仅 pending 触发）或 **L62 `amount > discount_threshold` 直接抛 TypeError——此处不在任何 try 内**，整个批处理中途崩停，前面所有结果丢失。
- 处方：入口做类型校验（`isinstance(amount, (int, float)) and not isinstance(amount, bool)`，或 `Decimal` 构造失败即 skip+log）；把"能崩溃的算术"全部置于校验之后。

**R5. 🔴 负金额过滤只覆盖 pending — L41-43**
- `status == "pending" and amount < 0` 才跳过；`completed`/其他状态的负 amount（退款单？脏数据？）会**畅通进入营收累加**，把 total_revenue 拉低甚至为负。是有意支持退款还是漏洞？契约不明即是风险。
- 处方：与业务确认负额语义；显式处理（退款单单独入账或一律 skip+log），不要靠状态巧合兜底。

**R6. 🟠 `top_value = -1` 哨兵值 — L122-127**
- 若所有客户总额 ≤ -1（负额订单场景，与 R5 联动完全可能），`top_customer` 返回 `None`，尽管客户存在；总额为 -1.0 的客户也选不出。
- 处方：`max(customer_totals, key=customer_totals.get, default=None)`（同 S19），无哨兵。

**R7. 🟠 `subtotal = amount + item_total` 疑似重复计价 — L90**
- 若 `amount` 本身已含条目总价（最常见的订单模型），条目价被**计了两次**，营收虚高；若 `amount` 是不含条目的基础价，则折扣/阈值只按基础价算（L62）而税按含条目价算，口径混杂。两种解释都说明契约未定义——这正是"没人敢动"的根源。
- 处方：向业务方确认 `amount` 与 `items` 的关系，写进 docstring 与测试；审查阶段标记为**最高优先级待澄清项**。

**R8. 🟠 `vip_total` 口径与其他总额不一致 — L78**
- `vip_total` 累加的是**折前、税前**的 `amount`，而 `total_revenue` 累加折后税前的 `final`。两个"总额"含义不同却并列返回，报表使用者极易误读。
- 处方：统一口径或改名 `vip_gross_amount`，并在返回契约中注明。

**R9. 🟠 重复标签叠加促销 — L82-88**
- `tags = ["SUMMER", "SUMMER"]` 减两次 5。上游若允许重复标签（或恶意构造），促销被放大。
- 处方：确认语义；若每单每种促销只应生效一次，先 `set(tags)` 或按去重后计。

**R10. 🟠 subtotal 可为负 → 负税，无下限保护 — L90-92**
- 促销 + 折扣叠加可超过 `amount + item_total`，得到负 subtotal，进而 `tax = subtotal * tax_rate` 为负"负税"，最终负 final 流入营收与客户累计。
- 处方：明确业务规则（clamp 到 0？允许负单走退款流程？），显式实现并测试。

**R11. 🟠 config 值零校验 — L12-15、L47**
- `tax_rate`/`discount_threshold` 若为 `None` 或字符串（配置中心常见事故），分别在 L91/L62 抛未捕获 TypeError；`vip_customers`/`blacklist_skus` 若为 `None`，L54/L72 迭代 None 崩溃。默认值只保护"键缺失"，不保护"键在但值坏"。
- 处方：入口处一次性校验并转换 config（`PricingConfig.from_dict`），坏配置 fail-fast 并给出明确错误信息，而不是在循环深处以奇怪的方式崩。

**R12. 🟠 重复订单 id 不设防 — L25、L104-115**
- 同一 id 出现两次会双份计入 revenue 与 customer_totals，无任何检测。上游重试/重放场景下这是真实资损点。
- 处方：确认契约；必要时用 `seen_ids` set 去重或报警。

**R13. 🟠 静默数据丢失无日志 — L32/36/39/42**
- 四类 skip 全部无声无息，生产中"今天营收怎么少了"将无从查起（与 S23 一体两面：S23 是可观测性设计，R13 是事故排查能力）。
- 处方：logging 记录每单 skip 原因与订单 id（采样或全量视规模）。

**R14. 🟡 top_customer 平局行为依赖 dict 插入序 — L124-127**
- 两个客户总额相同时，返回**先被处理**的那个（严格 `>` 不换人）。行为确定但未文档化，且随订单输入顺序变化。
- 处方：定义平局规则（如按 customer_id 字典序）写入契约与测试。

**R15. 🟡 `format_report` 对输入零防御 — L143-147**
- `data` 缺 `summary`/`total_revenue` 键直接 KeyError；fancy 分支不含 currency 与 tax，plain 分支用 `|` 分隔——若 summary 本身含 `|`（当前不含，但契约无保证）则解析歧义。与 `process_orders` 之间靠隐式 dict 形状耦合（Temporal/Contract Coupling）。
- 处方：让 `format_report` 接收 `process_orders` 的具名结果类型（dataclass/TypedDict），由类型系统保证键存在。

**R16. 🟡 `len(orders)` 要求 Sized 输入 — L22**
- 传入生成器/迭代器（流式读取大文件的自然写法）时 `len()` 直接 TypeError。当前实现把"必须是一次性列表"这个隐含契约埋进了循环写法里。
- 处方：`for order in orders:`（同 S16/P8）即天然支持任意可迭代对象。

---

## 四、修复优先级建议（供后续重构排期，本次未改任何文件）

1. **先锁行为再动刀**：补 characterization tests（S22），覆盖空列表、缺字段、坏类型、负额、平局、重复标签等边界。
2. **正确性第一批**（资损/事故级）：R1+R2（Decimal + 单一舍入点）、R3+R4（显式校验替代裸 except）、R5/R7/R10（业务口径澄清）。
3. **性能第一批**（设计期就该对的）：P1/P2（两个 Set）、P3（join）、P5（不变量外提）——四行改动把 O(N·(I·B+V)+S²) 降回 O(N·(I+T))。
4. **结构重构**：按 S1 拆函数、S8 建类型、S9/S10/S13 常量化，删除全部死代码（S5/S6/S7）。
5. **可观测性**：S23/R13（分类计数 + 日志）。

> 本报告仅为审查产物，未修改 `legacy.py` 或任何其他文件。
