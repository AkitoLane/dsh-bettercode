"""订单批处理 —— 由 legacy 屎山重构而来，对外行为与原版严格等价。

必须保留的 Legacy quirks（勿"顺手修复"，逐条有注释标记）：
- round(x, 2) 沿用 Python 银行家舍入口径；
- top_customer 从阈值 -1 起、严格大于才更新：平局取先插入的客户，
  所有客户总额 <= -1 时返回 None；
- 畸形订单 / amount 为 None / cancelled / pending 且负额 → 静默计入 skipped，
  不产生任何输出行；
- discount 兜底分支返回 int 0（而非 0.0），输出字段类型与原版一致；
- `amount == None` 用 == 而非 is，保持对重载 __eq__ 对象的行为对称。

性能取舍（Phase 4「结构换性能要自觉」）：
- 渐进复杂度改进：黑名单/VIP 判定由每单线性扫描 O(k) 降为集合 O(1)；
  summary 由二次方字符串累加（上万单时为 O(总长²) 的内存拷贝）降为
  逐行 append + 一次 join 的 O(n)。
- 代价：每单多若干次辅助函数调用与 NamedTuple 构造（微秒级常数开销）。
  在"orders 可达上万条"的规模下净收益为正，已用 10k 单基准实测（见交付报告）；
  热路径内所有比较顺序、运算顺序与原版逐字节一致，保证浮点结果与异常时机不变。
- 不 hashable 的 sku/customer_id 回退到原版的线性 == 扫描，行为不回退。
"""
from __future__ import annotations

from typing import NamedTuple

# ---- 业务常量（原版散落的魔法值，集中具名）----
DEFAULT_CURRENCY = "USD"
DEFAULT_TAX_RATE = 0.1
DEFAULT_DISCOUNT_THRESHOLD = 100

TIER1_DISCOUNT_RATE = 0.1  # amount > 阈值
TIER2_DISCOUNT_RATE = 0.05  # 阈值/2 < amount <= 阈值
VIP_DISCOUNT_RATE = 0.03

TAG_SUMMER = "SUMMER"
TAG_WINTER = "WINTER"
TAG_CLEARANCE = "CLEARANCE"
SUMMER_PROMO = 5
WINTER_PROMO = 3
CLEARANCE_PROMO = 10

STATUS_CANCELLED = "cancelled"
STATUS_PENDING = "pending"

ROUND_DECIMALS = 2
TOP_CUSTOMER_FLOOR = -1  # Legacy quirk: 初始阈值为 -1，总额全 <= -1 时无 top customer


class _OrderFields(NamedTuple):
    """一条订单里参与计算的字段（status 仅用于跳过判定）。"""
    order_id: object
    customer_id: object
    amount: object
    status: object
    items: object
    tags: object


class _PricingRules(NamedTuple):
    """从 config 一次性读出的计价参数与预建索引。"""
    currency: object
    tax_rate: object
    discount_threshold: object
    vip_customers: object  # 原始列表：不可 hash 场景的回退依据
    vip_index: object  # frozenset 或 None（元素不可 hash 时）
    blacklist_skus: object
    blacklist_index: object  # frozenset 或 None（元素不可 hash 时）


class _PricedOrder(NamedTuple):
    """单条订单的计价结果（未做最终 round，round 时机与原版一致）。"""
    subtotal: object
    tax: object
    final: object
    discount: object
    is_vip: bool


def _hash_index(values):
    """为 O(1) 成员判定建 frozenset 索引；values 含不可 hash 元素时返回 None。

    返回 None 时调用方回退到原版的线性 == 扫描，保持异常时机与比较语义不变。
    """
    try:
        return frozenset(values)
    except TypeError:
        return None


def _pricing_from_config(config) -> _PricingRules:
    # 读取顺序与原版一致：currency → tax_rate → discount_threshold → vip → blacklist
    vip_customers = config.get("vip_customers", [])
    blacklist_skus = config.get("blacklist_skus", [])
    return _PricingRules(
        config.get("currency", DEFAULT_CURRENCY),
        config.get("tax_rate", DEFAULT_TAX_RATE),
        config.get("discount_threshold", DEFAULT_DISCOUNT_THRESHOLD),
        vip_customers,
        _hash_index(vip_customers),
        blacklist_skus,
        _hash_index(blacklist_skus),
    )


def _extract_fields(order) -> _OrderFields:
    """按原版的字段读取顺序取值；缺键/畸形订单由此抛出，调用方计入 skipped。"""
    return _OrderFields(
        order["id"],
        order["customer_id"],
        order["amount"],
        order["status"],
        order.get("items", []),
        order.get("tags", []),
    )


def _should_skip(amount, status) -> bool:
    # Legacy quirk: `amount == None` 用 == 而非 is；短路顺序与原版三段 if 一致
    return (
        amount == None  # noqa: E711
        or status == STATUS_CANCELLED
        or (status == STATUS_PENDING and amount < 0)
    )


def _sku_is_blocked(sku, pricing) -> bool:
    if pricing.blacklist_index is not None:
        try:
            return sku in pricing.blacklist_index
        except TypeError:
            pass  # 不可 hash 的 sku：回退到原版的线性 == 扫描
    return any(entry == sku for entry in pricing.blacklist_skus)


def _items_subtotal(items, pricing):
    item_total = 0  # Legacy quirk: 从 int 0 起算，保持输出类型口径
    for item in items:
        # 三次 .get 的先后顺序与原版一致（异常时机对称）
        sku = item.get("sku")
        price = item.get("price", 0)
        qty = item.get("qty", 1)
        if not _sku_is_blocked(sku, pricing):
            item_total = item_total + price * qty
    return item_total


def _tier_discount(amount, threshold):
    # threshold / 2 刻意保留在每单内计算：提前到循环外会改变
    # 非数值 threshold 时的抛错时机（原版在第一条可处理订单才抛）。
    if amount > threshold:
        return amount * TIER1_DISCOUNT_RATE
    if amount > threshold / 2:
        return amount * TIER2_DISCOUNT_RATE
    return 0  # Legacy quirk: int 0（非 0.0），round 后输出仍为 int


def _is_vip(customer_id, pricing) -> bool:
    if pricing.vip_index is not None:
        try:
            return customer_id in pricing.vip_index
        except TypeError:
            pass  # 不可 hash 的 customer_id：回退到原版的线性 == 扫描
    return any(v == customer_id for v in pricing.vip_customers)


def _promo_total(tags):
    promo = 0
    for tag in tags:
        # 保留 == 比较链（而非 dict 查表）：不可 hash 的 tag 行为与原版一致
        if tag == TAG_SUMMER:
            promo = promo + SUMMER_PROMO
        elif tag == TAG_WINTER:
            promo = promo + WINTER_PROMO
        elif tag == TAG_CLEARANCE:
            promo = promo + CLEARANCE_PROMO
    return promo


def _price_order(fields: _OrderFields, pricing: _PricingRules) -> _PricedOrder:
    """计算单条订单的价格；各步骤顺序与原版严格一致（异常先后对称）。

    原版在 VIP 命中时立即累加 vip_total —— 由于其后任何一步抛异常都会
    终止整个调用、局部状态不可观测，累加安全地后移到主循环，加数顺序不变。
    """
    item_total = _items_subtotal(fields.items, pricing)
    discount = _tier_discount(fields.amount, pricing.discount_threshold)
    is_vip = _is_vip(fields.customer_id, pricing)
    vip_discount = 0
    if is_vip:
        vip_discount = (fields.amount - discount) * VIP_DISCOUNT_RATE
    promo = _promo_total(fields.tags)
    # 运算顺序不可调换：浮点加法不满足结合律，重排会改变末位精度
    subtotal = fields.amount + item_total - discount - vip_discount - promo
    tax = subtotal * pricing.tax_rate
    final = subtotal + tax
    return _PricedOrder(subtotal, tax, final, discount, is_vip)


def _summary_line(fields: _OrderFields, final_rounded, currency) -> str:
    # Legacy quirk: 用 str() 拼接而非 f-string/format，
    # 保证任意类型（自定义 __format__ 等）的输出口径与原版一致
    return ("order " + str(fields.order_id) + " cust " + str(fields.customer_id)
            + " final " + str(final_rounded) + " " + currency + ";")


def _order_record(fields: _OrderFields, priced: _PricedOrder, final_rounded) -> dict:
    # 键的插入顺序与 round 调用顺序均与原版一致
    return {
        "id": fields.order_id,
        "customer_id": fields.customer_id,
        "subtotal": round(priced.subtotal, ROUND_DECIMALS),
        "tax": round(priced.tax, ROUND_DECIMALS),
        "final": final_rounded,
        "is_vip": priced.is_vip,
        "discount": round(priced.discount, ROUND_DECIMALS),
    }


def _top_customer(customer_totals):
    # Legacy quirk: 从 -1 起、严格大于才更新 —— 平局取先插入的客户，
    # 所有总额 <= -1 时返回 None。不可改为 max()（口径不同）。
    top_customer = None
    top_value = TOP_CUSTOMER_FLOOR
    for customer_id, total in customer_totals.items():
        if total > top_value:
            top_value = total
            top_customer = customer_id
    return top_customer


def process_orders(orders: list[dict], config: dict) -> dict:
    """按 config 对 orders 逐单计价并汇总；对外行为与 legacy 原版严格等价。"""
    pricing = _pricing_from_config(config)
    records: list = []
    summary_lines: list = []  # 逐行收集、最后 join：消除原版 O(n²) 字符串累加
    customer_totals: dict = {}
    total_revenue = 0  # Legacy quirk: int 0 起算（空批时输出 round(0) 为 int）
    total_tax = 0
    vip_total = 0
    skipped = 0

    for order in orders:
        try:
            fields = _extract_fields(order)
        except Exception:
            # Legacy quirk: 原版用裸 except 吞掉一切读取错误并计入 skipped；
            # 收窄为 Exception（不再吞 KeyboardInterrupt/SystemExit），
            # 对数据类输入的跳过计数行为不变。
            skipped = skipped + 1
            continue

        if _should_skip(fields.amount, fields.status):
            skipped = skipped + 1
            continue

        priced = _price_order(fields, pricing)
        if priced.is_vip:
            vip_total = vip_total + fields.amount

        final_rounded = round(priced.final, ROUND_DECIMALS)
        summary_lines.append(_summary_line(fields, final_rounded, pricing.currency))

        # Legacy quirk: 首次直接存 final 本身（不做 0 + final），
        # 保持 -0.0 等类型口径；不可 hash 的 customer_id 在此抛 TypeError，与原版同点位
        if fields.customer_id in customer_totals:
            customer_totals[fields.customer_id] = customer_totals[fields.customer_id] + priced.final
        else:
            customer_totals[fields.customer_id] = priced.final

        records.append(_order_record(fields, priced, final_rounded))

        total_revenue = total_revenue + priced.final
        total_tax = total_tax + priced.tax

    return {
        "results": records,
        "summary": "".join(summary_lines),
        "total_revenue": round(total_revenue, ROUND_DECIMALS),
        "total_tax": round(total_tax, ROUND_DECIMALS),
        "skipped": skipped,
        "vip_total": round(vip_total, ROUND_DECIMALS),
        "customer_totals": {k: round(v, ROUND_DECIMALS) for k, v in customer_totals.items()},
        "top_customer": _top_customer(customer_totals),
        "count": len(records),
        "currency": pricing.currency,
    }


def _format_report_fancy(data) -> str:
    return "=== REPORT ===\n" + data["summary"] + "\nTotal: " + str(data["total_revenue"])


def _format_report_plain(data) -> str:
    return data["summary"] + "|" + str(data["total_revenue"])


def format_report(data, fancy):
    """Legacy 兼容层：布尔参数 fancy 属冻结签名（外部调用方按位置/关键字传参）。

    布尔陷阱已拆为上面两个语义函数，本函数仅做薄适配；参数名与真值判定口径不变。
    """
    if fancy:
        return _format_report_fancy(data)
    return _format_report_plain(data)
