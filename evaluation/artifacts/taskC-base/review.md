# legacy.py 代码审查报告

- 审查对象:`legacy.py`(147 行,含 `process_orders` 与 `format_report` 两个函数)
- 审查方式:逐行静态审查,未修改任何文件
- 结论概览:**坏味道 24 条,性能问题 7 条,风险点 15 条**。最严重的三类问题是:①用 float 做金额运算且各处舍入口径不一致(对账必出差额);②裸 `except:` 会把编程错误吞成"整批订单静默跳过";③`summary` 字符串循环拼接导致 O(N²) 退化,大批量订单下会同时打爆 CPU 和内存。

严重程度标记:🔴 严重 / 🟠 较高 / 🟡 中 / ⚪ 低。各清单内部已按严重程度降序排列。

---

## 一、坏味道清单(24 条)

### S1 🟠 裸 `except:` 捕获一切异常 — L24–L33
- **症状**:`try` 包住字段提取,`except:` 不指定任何异常类型,直接 `skipped += 1; continue`。
- **病因**:图省事的防御式写法;把"数据缺字段"和"代码写错"混为一谈。它会连带捕获 `KeyboardInterrupt`、`SystemExit`,还会吞掉未来的键名笔误(如 `customer_ID`),让程序"正常运行"却输出空报告。
- **处方**:只捕获预期异常并记录上下文:`except (KeyError, TypeError) as e: logger.warning("skip order %r: %s", order, e)`;按原因分类计数;对 skipped 比例设置告警阈值。

### S2 🟠 上帝函数:`process_orders` 一个函数干十件事 — L4–L140
- **症状**:约 137 行,混合了配置读取、字段解析、校验、商品小计、折扣、VIP、促销、税、摘要拼接、按客户聚合、找 top customer、组装返回值。局部变量 15+ 个。
- **病因**:典型的"没人敢动"式堆积——每次需求都在原函数里追加,从未拆分;无法单元测试任何一条业务规则。
- **处方**:按职责拆成纯函数:`extract_order(order)`、`is_skippable(order)`、`item_subtotal(items, blacklist)`、`calc_discount(amount, cfg)`、`calc_vip(...)`、`calc_promo(tags)`、`aggregate(...)`;主函数只做编排。每个纯函数可独立测试。

### S3 🟠 魔法数字散布全文,业务规则硬编码 — L13、L62–L66、L77、L84–L88
- **症状**:折扣率 `0.1`/`0.05`、半阈值 `/2`、VIP 率 `0.03`、促销额 `5/3/10` 直接写死在逻辑分支里。
- **病因**:规则、阈值、费率没有集中定义;改一个促销额度要在函数中部动刀,容易误伤相邻分支。
- **处方**:提取模块级常量(`VIP_RATE = 0.03`)或并入 `config`(与 `tax_rate`、`discount_threshold` 同级);促销改为映射表 `PROMO_VALUES = {"SUMMER": 5, "WINTER": 3, "CLEARANCE": 10}`。

### S4 🟡 校验逻辑与业务逻辑纠缠,try 块范围错误 — L24–L43
- **症状**:`try` 只包住取字段,但真正会因脏数据抛异常的比较(`amount < 0`,L41)和算术(L62、L90)在 try 之外;校验分散在 4 个 `if ... skipped += 1; continue`。
- **病因**:异常边界是按"写代码时的顺序"划的,不是按"失败模式"划的。
- **处方**:解析后立即做类型/取值校验(见 R3、R4),校验集中为一个返回 `(ok, reason)` 的函数。

### S5 🟡 `skipped = skipped + 1; continue` 重复 4 次 — L32、L36、L39、L42
- **症状**:同一段计数+跳过样板出现 4 处,且 `skipped` 不区分原因。
- **病因**:缺少统一的过滤/校验出口;排查生产问题时无法知道订单为何被跳过。
- **处方**:`reason = skip_reason(order); if reason: skip_counts[reason] += 1; continue`,用 Counter 按原因分桶。

### S6 🟡 C 风格索引循环 — L22–L23
- **症状**:`for i in range(len(orders)): order = orders[i]`,索引 `i` 再无他用。
- **病因**:从其他语言带来的习惯写法;还顺带要求 `orders` 必须支持 `len()` 和下标(排除生成器)。
- **处方**:`for order in orders:`;确需索引用 `enumerate(orders)`。

### S7 🟡 `amount == None` 而非 `is None` — L35
- **症状**:用 `==` 与 `None` 比较。
- **病因**:`==` 走 `__eq__`,可被自定义类型重载(如 numpy 数组会返回数组),产生意外真值;PEP 8 明确要求单例比较用 `is`。
- **处方**:改为 `if amount is None:`。

### S8 🟡 `if is_vip == True:` — L76
- **症状**:布尔值与 `True` 做相等比较。
- **病因**:同上,违反 PEP 8;若 `is_vip` 是 truthy 非布尔值还会漏判。
- **处方**:改为 `if is_vip:`。

### S9 🟡 循环体内重复读取不变的配置 — L47
- **症状**:`blacklist = config.get("blacklist_skus", [])` 写在订单循环内部,每单重新取一次。
- **病因**:添加黑名单功能时就近取配置,忘了它对所有订单是常量。
- **处方**:与 L12–L15 的其他配置读取一起提到循环外,并顺手转成 `set`(见 P2)。

### S10 🟡 内层查找循环命中后不 break — L54–L57、L72–L74
- **症状**:黑名单命中置 `blocked = True` 后继续扫完剩余条目;VIP 命中后同样继续扫。
- **病因**:用"手写线性查找 + 标志位"而不是语言内置的成员判断。
- **处方**:改 `if sku in blacklist_set:` / `is_vip = cust in vip_set:`,既消除无谓比较,也把复杂度降为 O(1)(见 P2、P3)。

### S11 🟡 冗余的 else 分支与重复初始化 — L61、L64–L68
- **症状**:`discount = 0` 在 L61 已初始化,L68 的 `else: discount = 0` 再赋一次;两档折扣写成嵌套 if/else 三层深。
- **病因**:分支是逐年"打补丁"长出来的,没人回头整理。
- **处方**:扁平化为 `if amount > threshold: ... elif amount > threshold / 2: ...`,删掉多余 else。

### S12 🟡 `in dict.keys()` 冗余 + 手写累加 — L99–L102、L124
- **症状**:`if cust in customer_totals.keys()` 再手写 if/else 累加。
- **病因**:Python 2 时代习惯残留;`keys()` 在 Py3 是视图(无害但冗余),在 Py2 会物化列表变 O(n)。
- **处方**:`customer_totals[cust] = customer_totals.get(cust, 0.0) + final`,或 `collections.defaultdict(float)` / `Counter`;遍历用 `for c in customer_totals:`。

### S13 🟡 促销规则用 if/elif 链而非查表 — L82–L88
- **症状**:每个标签一个分支,新标签必须改函数体。
- **病因**:规则与代码耦合。
- **处方**:`promo = sum(PROMO_VALUES.get(t, 0) for t in tags)`。

### S14 🟡 摘要行用 `+` 与 `str()` 手工拼接 — L95
- **症状**:6 段字符串相加,可读性差,易漏分隔符。
- **病因**:未使用 f-string。
- **处方**:`line = f"order {oid} cust {cust} final {final:.2f} {currency};"`(注意 `:.2f` 与 `round` 的显示差异,见 R2)。

### S15 🟡 死代码:`if False:` 调试分支 — L117–L119
- **症状**:永远不会执行的 print。
- **病因**:调试代码被"关死"而不是删除。
- **处方**:整块删除;需要调试输出用 `logging.debug`。

### S16 🟡 注释掉的代码 — L18–L20
- **症状**:`apply_rounding` 旧逻辑以注释形式留存。
- **病因**:不敢删,靠注释"留档"。
- **处方**:删除,历史交给版本控制;若该开关仍可能恢复,应写成 ticket 而非注释。

### S17 ⚪ 过期的 TODO — L5
- **症状**:"TODO: clean this up later - original author left 2023",无负责人、无追踪号,已陈化多年。
- **病因**:TODO 没有进入任务系统就等于永远不会做。
- **处方**:转为正式工单(本次审查即可作为依据),然后删除注释。

### S18 ⚪ 注释与实现不符 — L121
- **症状**:注释说 "find top customer by scanning repeatedly",实现只是单次 O(C) 扫描。
- **病因**:可能曾有 O(C²) 实现被优化过,注释没跟上;误导后续维护者。
- **处方**:更正为"single pass"或直接删注释;实现可简化为 `max(customer_totals.items(), key=..., default=(None, -1))`。

### S19 ⚪ 基本类型偏执:返回 10 键大字典 — L129–L140
- **症状**:调用方只能靠字符串键访问,拼错键名要到运行时才炸;字段结构无任何声明。
- **病因**:缺乏领域模型。
- **处方**:定义 `@dataclass ReportSummary`(或 TypedDict),字段名获得 IDE 与类型检查支持。

### S20 ⚪ `format_report(data, fancy)` 的布尔旗标参数 — L143–L147
- **症状**:一个布尔开关切换两种完全不同的输出格式;调用点 `format_report(d, True)` 可读性为零。
- **病因**:两个功能被硬塞进一个函数。
- **处方**:拆成 `format_report_plain(data)` 与 `format_report_fancy(data)`,或接受枚举/格式策略。

### S21 ⚪ 无类型注解、无 docstring、无契约说明 — 全文件
- **症状**:`orders`、`config` 的结构只能逐行反推(哪些键必填、哪些有默认值、类型是什么)。
- **病因**:遗留代码从未补文档。
- **处方**:为 `config` 定义 TypedDict,为订单项定义结构,补 docstring 说明跳过规则、折扣叠加顺序、税费口径。

### S22 ⚪ `vip_total` 口径含混 — L78
- **症状**:累加的是未扣任何折扣的 `amount` 原价,与 `results` 里的实付口径不一致;名字却叫 "vip_total"。
- **病因**:统计需求临时加,语义没定义清楚。
- **处方**:确认业务想要"VIP 原价总额"还是"VIP 实付总额",并改名(如 `vip_gross_amount`)。

### S23 ⚪ 冗余派生字段 `count` — L138
- **症状**:`count == len(results)`,永远可由 `results` 推出。
- **病因**:为调用方"方便"预计算,但制造了两处真相,存在不一致的可能。
- **处方**:删除,或在 dataclass 中做成 `property`。

### S24 ⚪ `currency` 只进摘要字符串,不进结构化结果 — L95、L104–L112
- **症状**:每条 `results` 记录没有货币字段,金额语义不完整;下游无法按币种解析。
- **病因**:摘要字符串是给人看的,结构化数据却缺了同一信息。
- **处方**:在返回体或每条 result 中携带 currency;多币种订单需先统一换算(当前代码完全没处理)。

---

## 二、性能问题清单(7 条)

记号:N = 订单数,I = 平均每单商品数,B = 黑名单长度,V = VIP 客户数,C = 去重客户数,L = 平均摘要行长。

### P1 🔴 `summary` 循环字符串拼接 — O(N²) — L96
- **问题**:字符串不可变,`summary = summary + line` 每次都完整复制已有内容。处理 N 单的总复制量约为 `N²·L/2` 字节。
- **规模退化**:1 千单 ≈ 可忽略;10 万单、每行 60 字节时,最终串约 6 MB,但累计复制约 300 GB 字节搬运,CPU 呈平方增长;同时中间副本让内存峰值翻倍,可能触发频繁 GC 甚至 OOM。这是全文件最致命的一处性能炸弹。
- **处方**:`lines = []` → `lines.append(line)` → 结束时 `summary = "".join(lines)`,总复杂度 O(N·L),join 一次分配。

### P2 🟠 黑名单逐项线性扫描 — O(N·I·B) — L48–L57
- **问题**:每个订单的每个商品都完整遍历黑名单列表(且命中后不 break,见 P5)。
- **规模退化**:B = 1 万、N = 10 万、I = 5 时约 5×10⁹ 次比较,分钟级甚至更久;B 增长时线性恶化,与 P1 叠加成平方×线性。
- **处方**:循环外 `blacklist_set = set(config.get("blacklist_skus", []))`(一次性 O(B)),查成员 `sku in blacklist_set` O(1);总代价降为 O(N·I)。

### P3 🟠 VIP 客户线性扫描 — O(N·V) — L72–L74
- **问题**:每个订单遍历整个 VIP 列表判断成员资格。
- **规模退化**:V = 10 万会员、N = 10 万订单时约 10¹⁰ 次比较,不可接受;会员规模增长直接拖垮下单批处理。
- **处方**:循环外 `vip_set = set(vip_customers)`,`is_vip = cust in vip_set`,总代价 O(N)。

### P4 🟡 循环内重复 `config.get("blacklist_skus", [])` — O(N) 次冗余查找 — L47
- **问题**:配置在整个批处理中不变,却每单取一次;单次很便宜(dict 查找),但纯属浪费,且掩盖了"黑名单应预处理成 set"的事实。
- **规模退化**:随 N 线性增长的常数项开销;真正的危害是与 P2 复合。
- **处方**:提到循环外(与 L12–L15 并列),一次读取并转换。

### P5 🟡 命中后不停止扫描 — 平均多扫一半 — L54–L57、L72–L74
- **问题**:黑名单/VIP 命中置标志后循环继续跑完,期望浪费约 B/2、V/2 次比较;黑名单命中(要剔除的 SKU)恰恰是最该早停的场景。
- **规模退化**:不改变渐进复杂度,但把 P2/P3 的常数因子放大最多 2 倍。
- **处方**:改用 set 成员判断后此问题自动消失;若保留循环则命中即 `break`。

### P6 🟡 全量数据驻留内存,摘要串反复复制 — O(N) 内存、峰值翻倍 — L96、L104、L145
- **问题**:`results` 列表 + 巨型 `summary` 字符串同时驻留;P1 的中间副本使峰值内存约为最终串的 2 倍;`format_report` 的 `"===..." + data["summary"] + ...`(L145)又整体复制一次摘要串。
- **规模退化**:百万级订单时,摘要串可达数百 MB,复制链上同时存在 2–3 份,内存压力成倍放大。
- **处方**:存 `lines` 列表,由 `format_report` 决定 join 时机;或流式写出/分页返回,避免"全量字符串化"。

### P7 ⚪ top customer 扫描本身没问题,但可更简洁 — O(C) — L122–L127
- **问题**:单次遍历 O(C) 是正确复杂度(注释"scanning repeatedly"是错的);仅指出可用内置写法。
- **处方**:`top_customer = max(customer_totals, key=customer_totals.get, default=None)`(注意 default 与 R10 的 -1 边界问题一并处理)。

**总体复杂度评估**:当前实现为 **O(N²·L) 时间(P1 主导)+ O(N·I·B + N·V)**;三处修复(列表 join、两个 set)后可降至 **O(N·(I+V⁰+L)) ≈ O(N)** 线性,是完全可达到的目标。

---

## 三、风险点(15 条)

### R1 🔴 用 float 做金额运算 + `round()` 银行家舍入 — 全文(L63、L77、L84–L88、L91、L95、L107–L109、L132–L136)
- **风险**:二进制浮点无法精确表示 0.1、0.03 等十进制小数,乘法与累加会引入并放大误差;Python `round()` 是 round-half-even,且 `round(2.675, 2) == 2.67`(因 2.675 实际存储为 2.67499…)。生产表现:财务对账差几分钱、同一金额在不同路径舍入结果不同、税务申报数字不可复现。
- **处方**:全链路改用 `Decimal`(务必用字符串构造 `Decimal("0.03")`),或以"分"为单位的整数运算;舍入模式显式指定(财务通常要 ROUND_HALF_UP)。

### R2 🔴 舍入口径不一致:明细先舍入、汇总后舍入 — L107–L109 vs L114–L115 vs L132–L136
- **风险**:`results` 里每条 `final` 是 `round(final, 2)`,而 `total_revenue`、`customer_totals` 累加的是未舍入值、最后才 round。**逐单明细相加 ≠ 返回的总计**,差额随 N 增大而累积(每单最多 ±0.005)。下游对账、报表核对必然周期性发现"不平",且无法定位。
- **处方**:统一口径并写入文档——要么全部"先舍入再累加"(财务明细常用),要么全部"累加原始值最后舍入",二者选其一贯彻到底。

### R3 🔴 裸 `except:` 把编程错误吞成静默数据丢失 — L24–L33
- **风险**:这是最阴险的失败模式:未来任何人改错一个键名、或上游变更字段结构,**所有订单都会被无声跳过**,函数照常返回 `results=[]、skipped=N` 的"合法"报告,没有任何异常、日志或告警。系统看起来在正常运行,业务数据实际全丢。
- **处方**:见 S1;另外对 `skipped / len(orders)` 比例设阈值告警(如 >5% 即报错),让静默失败变成显式失败。

### R4 🟠 `amount` 为非数值类型时未捕获的 TypeError,整批崩溃 — L41、L62、L90
- **风险**:try 块只覆盖取字段(L24–L33);之后 `amount < 0`(L41)、`amount > discount_threshold`(L62)、`amount + item_total`(L90)都在保护之外。一条脏数据 `{"amount": "100", "status": "pending"}` 就让**整个批处理抛 TypeError 中断**,前面所有订单的结果全部丢弃。
- **处方**:解析后立即校验 `isinstance(amount, (int, float)) and not isinstance(amount, bool)`,不合格走 skipped 通道。

### R5 🟠 字段值为显式 `None` 时崩溃,`.get` 默认值失效 — L29–L30、L48–L51、L82
- **风险**:`order.get("items", [])` 只在**键缺失**时给默认值;`{"items": None}` 返回 None,`for it in items` 抛 TypeError(在 try 之外,整批崩溃)。同理 `{"price": None}` 时 `price * qty` 抛 TypeError;`tags=None` 同理。上游 JSON 序列化 null 字段是极常见的场景。
- **处方**:`items = order.get("items") or []`,`price = it.get("price") or 0`,并校验类型。

### R6 🟠 疑似双重计费:`amount + item_total` — L90
- **风险**:若 `amount` 语义是"订单总额"(已含各商品价),再加 `item_total` 会把商品金额算两遍,营收虚增近一倍——这是直接的资损/报表错误。代码没有任何注释说明 `amount` 与 `items` 的关系,两种解读都能自圆其说。
- **处方**:与业务方确认口径并在 docstring 写明;若 amount 不含商品价,建议改名 `base_amount` 消除歧义;并补一条"已知输入 → 期望输出"的黄金测试锁定语义。

### R7 🟠 负数金额订单可进入计价流程,产生负税 — L41–L43、L90–L92
- **风险**:只有 `status == "pending" and amount < 0` 被跳过;`completed`/`refunded` 状态的负金额订单照常计算,得出负的 subtotal、**负的 tax**(负税额在财务上无意义)、负的 final,污染 `total_revenue`、`customer_totals`,还会触发 R10。退款是正常业务,但应有独立的冲销逻辑而不是走正向计价。
- **处方**:明确负金额语义;退款单独分支处理(冲减营收、冲减税额),或对 `subtotal` 做 `max(0, ...)` 钳制(按业务定)。

### R8 🟡 `tags` 为字符串时静默失效 — L82–L88
- **风险**:上游传 `"tags": "SUMMER"`(字符串而非列表)时,`for t in tags` 迭代出单个字符,全部不匹配,promo=0——**不报错、不留痕**,该给的促销没给,客诉后极难排查。
- **处方**:校验 `isinstance(tags, list)`;或防御性地 `if isinstance(tags, str): tags = [tags]`,并记录警告。

### R9 🟡 折扣阈值边界为严格大于,语义未声明 — L62、L65
- **风险**:`amount == discount_threshold`(恰好 100)拿不到 10% 档,`amount == threshold/2`(恰好 50)拿不到 5% 档。边界归属没有文档,运营调整 `discount_threshold` 配置后边界订单行为悄然改变,容易产生客诉或套利。
- **处方**:与业务确认 `>=` 还是 `>`,写入 docstring,并用边界值测试(49.99/50/100/100.01)锁定。

### R10 🟡 `top_value = -1` 初始化导致 top_customer 误报 None — L122–L127
- **风险**:结合 R7,若所有客户累计额都 ≤ -1(退款占主导时可能出现),循环永远不满足 `> top_value`,返回 `top_customer: None`,掩盖真实(哪怕是负的)第一名。空 `customer_totals` 返回 None 是合理的,但"有客户却返回 None"是错误。
- **处方**:用 `max(customer_totals.items(), key=operator.itemgetter(1), default=(None, None))`,或初始化 `top_value = float("-inf")`。

### R11 🟡 VIP 折扣叠加顺序是隐式业务决策 — L77
- **风险**:`vip_discount = (amount - discount) * 0.03` 意味着 VIP 折扣**叠加在普通折扣之后**、且只对 `amount` 部分打折(不含 `item_total`,也不被 promo 影响)。若业务意图是"取两者较大"或"对实付总额打折",当前实现就是错的。三个折扣的先后次序完全没有文档。
- **处方**:确认规则,写成显式的、有名字的计价管线(discount → vip → promo → tax),每步单元测试。

### R12 🟡 税基与促销平减额口径存疑 — L84–L88、L91
- **风险**:促销 5/3/10 是**无货币单位的平减额**——currency 配置为 EUR/JPY 时这些数字是什么含义?JPY 通常无小数,"减 5"与 `round(x, 2)` 都失去意义。另外税按扣除全部折扣后的 subtotal 计征,是否符合当地税务规则无人能确认。
- **处方**:促销额应随币种配置化;税基规则写入 docstring 并经财务确认;多币种场景需引入汇率换算(当前完全缺失)。

### R13 🟡 入口无契约校验:`orders`/`config` 本身可能是坏值 — L4、L12、L22
- **风险**:`orders=None` → `len(None)` TypeError;`orders` 是 dict → 迭代出键、全部进 except 被静默跳过(回到 R3);`config=None` → L12 `config.get` 直接崩溃。函数对入参没有任何假设声明。
- **处方**:入口处断言/校验类型,docstring 声明契约;或用 TypedDict + 类型注解让静态检查兜底。

### R14 ⚪ `format_report` 的 KeyError 与浮点长尾 — L143–L147
- **风险**:直接 `data["summary"]`、`data["total_revenue"]` 下标访问,传入不含这些键的 dict(或 R3 场景下的残缺数据)即崩溃;`str(data["total_revenue"])` 对 float 可能输出 `105.30000000000001` 之类的长尾,报表观感差且下游字符串解析会出错。
- **处方**:金额格式化统一 `f"{value:.2f}"`(配合 R1 改 Decimal 后用 quantize);对缺键给出明确报错信息。

### R15 ⚪ 零可观测性、零测试 — 全文件
- **风险**:没有 logging、没有任何测试、唯一的调试输出在 `if False:` 死代码里(L117–L119)。上述 R1–R14 任何一个在生产爆发时,都无法回答"是哪一单、哪一步出的问题";任何修复也没有回归保障。对"没人敢动"的代码,缺测试正是没人敢动的根源。
- **处方**:先补特征测试(characterization tests)锁定当前行为,再做任何清理;关键路径(跳过、折扣、税、汇总)加结构化日志。

---

## 附:修复优先级建议(不改动代码,仅供排期参考)

| 优先级 | 事项 | 对应条目 |
|---|---|---|
| P0 | 金额改 Decimal/整数分,统一舍入口径 | R1、R2 |
| P0 | 裸 except 改精确捕获 + skipped 比例告警 | R3、S1 |
| P0 | 脏数据防护:amount/items/tags/price 类型校验 | R4、R5、R8 |
| P1 | summary 改 list+join;黑名单/VIP 改 set 并提到循环外 | P1、P2、P3、P4、P5 |
| P1 | 与业务确认 amount+item_total 口径、负金额/退款流程、折扣叠加顺序 | R6、R7、R9、R11、R12 |
| P2 | 拆分上帝函数、消除死代码/魔法数、补类型注解与特征测试 | S2–S24、R15 |
