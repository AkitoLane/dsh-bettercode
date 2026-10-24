"""订单批处理：给一批订单计价，并聚合成对账用的汇总结果。

对外契约与重构前逐字段一致：``process_orders`` / ``format_report`` 的返回值、
键顺序、异常类型与抛出时机都不变，连 ``round`` 作用在 int 上仍返回 int 这种
细节也保持一致（``test_legacy.py`` 是锁定该行为的特征测试）。

复杂度（N 条订单，每条 I 个 item，黑名单 B 项，VIP 名单 V 项）：
原版是 O(N·(I·B + V))，摘要串用 ``+=`` 累加是 O(N²)；这里把两个名单换成
集合索引、摘要改成 list + join，降到 O(N·I) 与 O(N)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

_DEFAULT_CURRENCY = "USD"
_DEFAULT_TAX_RATE = 0.1
_DEFAULT_DISCOUNT_THRESHOLD = 100

# 折扣分档：过门槛打 9 折，过半门槛打 95 折。
_DISCOUNT_RATE_OVER_THRESHOLD = 0.1
_DISCOUNT_RATE_OVER_HALF_THRESHOLD = 0.05
_VIP_DISCOUNT_RATE = 0.03

# 标签促销：同一订单的多个标签可叠加，但单个标签只命中一档（原版是 if/elif）。
_PROMO_AMOUNT_BY_TAG = (("SUMMER", 5), ("WINTER", 3), ("CLEARANCE", 10))

_STATUS_CANCELLED = "cancelled"
_STATUS_PENDING = "pending"

# 原版选"消费最高客户"时用它当下限：所有客户累计额都 <= -1 时不选出任何人。
_TOP_CUSTOMER_VALUE_FLOOR = -1

_DETAILED_REPORT_HEADING = "=== REPORT ==="


class _OrderInputs(NamedTuple):
    """从一条原始订单里取出的、计价需要的字段。"""

    order_id: Any
    customer_id: Any
    amount: Any
    status: Any
    items: Any
    tags: Any


class _PricingRules(NamedTuple):
    """一次批处理内不变的配置：币种、税率、折扣门槛与两个名单判定。"""

    currency: Any
    tax_rate: Any
    discount_threshold: Any
    is_vip_customer: Callable[[Any], bool]
    is_blacklisted_sku: Callable[[Any], bool]


class _PricedOrder(NamedTuple):
    """一条订单的计价结果（未取整的原始值）。"""

    discount: Any
    is_vip: bool
    subtotal: Any
    tax: Any
    final: Any


def _build_member_test(values: Any) -> Callable[[Any], bool]:
    """构造等价于 ``any(v == target for v in values)`` 的判定函数，但命中是 O(1)。

    原版对每个 item 扫一遍黑名单、对每条订单扫一遍 VIP 名单，是 N·B 与 N·V
    的隐藏平方项。集合查找与 ``==`` 在可哈希对象上等价；名单项或查询值不可
    哈希时（例如 list 型 sku）退回线性 ``==`` 扫描，语义与原版完全相同。
    """
    if not isinstance(values, (list, tuple, set, frozenset)):
        # 一次性迭代器之类不能安全物化成索引：保持逐次线性比较。
        return lambda target: any(v == target for v in values)

    try:
        index = frozenset(values)
    except TypeError:
        return lambda target: any(v == target for v in values)

    def is_member(target: Any) -> bool:
        try:
            return target in index
        except TypeError:
            return any(v == target for v in values)

    return is_member


def _pricing_rules_from(config: Any) -> _PricingRules:
    return _PricingRules(
        currency=config.get("currency", _DEFAULT_CURRENCY),
        tax_rate=config.get("tax_rate", _DEFAULT_TAX_RATE),
        discount_threshold=config.get("discount_threshold", _DEFAULT_DISCOUNT_THRESHOLD),
        is_vip_customer=_build_member_test(config.get("vip_customers", [])),
        is_blacklisted_sku=_build_member_test(config.get("blacklist_skus", [])),
    )


def _read_order_inputs(order: Any) -> _OrderInputs | None:
    """取出必需字段；订单不是映射或缺字段时返回 None（原版把它计入 skipped）。"""
    try:
        return _OrderInputs(
            order_id=order["id"],
            customer_id=order["customer_id"],
            amount=order["amount"],
            status=order["status"],
            items=order.get("items", []),
            tags=order.get("tags", []),
        )
    except Exception:
        return None


def _should_skip(amount: Any, status: Any) -> bool:
    """原版的三条跳过规则：无金额、已取消、待付且金额为负。"""
    if amount is None:
        return True
    if status == _STATUS_CANCELLED:
        return True
    return status == _STATUS_PENDING and amount < 0


def _billable_items_total(items: Any, is_blacklisted_sku: Callable[[Any], bool]) -> Any:
    total = 0
    for item in items:
        sku = item.get("sku")
        price = item.get("price", 0)
        qty = item.get("qty", 1)
        if not is_blacklisted_sku(sku):
            total = total + price * qty
    return total


def _tier_discount(amount: Any, discount_threshold: Any) -> Any:
    if amount > discount_threshold:
        return amount * _DISCOUNT_RATE_OVER_THRESHOLD
    # 门槛的一半每次现算：提前算会改变 threshold 非法时的抛错时机。
    if amount > discount_threshold / 2:
        return amount * _DISCOUNT_RATE_OVER_HALF_THRESHOLD
    return 0


def _promo_total(tags: Any) -> Any:
    total = 0
    for tag in tags:
        for promo_tag, promo_amount in _PROMO_AMOUNT_BY_TAG:
            if tag == promo_tag:
                total = total + promo_amount
                break
    return total


def _price_order(order: _OrderInputs, rules: _PricingRules) -> _PricedOrder:
    """纯函数：算出一条订单的折扣、小计、税与最终金额，不碰任何累加器。"""
    # 各步骤顺序照抄原版：畸形数据抛出的异常类型与先后必须一致。
    items_total = _billable_items_total(order.items, rules.is_blacklisted_sku)
    discount = _tier_discount(order.amount, rules.discount_threshold)
    is_vip = rules.is_vip_customer(order.customer_id)
    vip_discount = (order.amount - discount) * _VIP_DISCOUNT_RATE if is_vip else 0
    promo = _promo_total(order.tags)
    subtotal = order.amount + items_total - discount - vip_discount - promo
    tax = subtotal * rules.tax_rate
    return _PricedOrder(
        discount=discount,
        is_vip=is_vip,
        subtotal=subtotal,
        tax=tax,
        final=subtotal + tax,
    )


def _order_result(order: _OrderInputs, priced: _PricedOrder) -> dict:
    return {
        "id": order.order_id,
        "customer_id": order.customer_id,
        "subtotal": round(priced.subtotal, 2),
        "tax": round(priced.tax, 2),
        "final": round(priced.final, 2),
        "is_vip": priced.is_vip,
        "discount": round(priced.discount, 2),
    }


def _summary_line(order: _OrderInputs, priced: _PricedOrder, currency: Any) -> str:
    # 保留原版的 + 拼接表达式：currency 不是 str 时原版抛 TypeError，这里必须一致。
    return (
        "order " + str(order.order_id) + " cust " + str(order.customer_id)
        + " final " + str(round(priced.final, 2)) + " " + currency + ";"
    )


def _top_customer(customer_totals: dict) -> Any:
    """累计额最高的客户；并列时取先出现的那个，全都 <= -1 时返回 None。"""
    top_customer = None
    top_value = _TOP_CUSTOMER_VALUE_FLOOR
    for customer_id, total in customer_totals.items():
        if total > top_value:
            top_value = total
            top_customer = customer_id
    return top_customer


def process_orders(orders: list[dict], config: dict) -> dict:
    """给一批订单计价并聚合，返回逐单结果、摘要串与各项汇总。"""
    rules = _pricing_rules_from(config)

    results: list[dict] = []
    summary_lines: list[str] = []
    customer_totals: dict = {}
    total_revenue = 0
    total_tax = 0
    vip_revenue = 0
    skipped = 0

    for order in orders:
        inputs = _read_order_inputs(order)
        if inputs is None or _should_skip(inputs.amount, inputs.status):
            skipped += 1
            continue

        priced = _price_order(inputs, rules)
        results.append(_order_result(inputs, priced))
        summary_lines.append(_summary_line(inputs, priced, rules.currency))

        customer_id = inputs.customer_id
        if customer_id in customer_totals:
            customer_totals[customer_id] += priced.final
        else:
            customer_totals[customer_id] = priced.final

        total_revenue += priced.final
        total_tax += priced.tax
        if priced.is_vip:
            vip_revenue += inputs.amount

    return {
        "results": results,
        "summary": "".join(summary_lines),
        "total_revenue": round(total_revenue, 2),
        "total_tax": round(total_tax, 2),
        "skipped": skipped,
        "vip_total": round(vip_revenue, 2),
        "customer_totals": {
            customer_id: round(total, 2) for customer_id, total in customer_totals.items()
        },
        "top_customer": _top_customer(customer_totals),
        "count": len(results),
        "currency": rules.currency,
    }


def format_report(data: dict, fancy: bool) -> str:
    """把 process_orders 的结果渲染成报表文本。

    ``fancy`` 是历史遗留的布尔开关，调用方已按位置传参，签名保持不变；
    内部拆成两个具名渲染函数，免得两套字符串逻辑挤在一个 if/else 里。
    """
    return _render_detailed_report(data) if fancy else _render_compact_report(data)


def _render_detailed_report(data: dict) -> str:
    return (
        _DETAILED_REPORT_HEADING + "\n" + data["summary"]
        + "\nTotal: " + str(data["total_revenue"])
    )


def _render_compact_report(data: dict) -> str:
    return data["summary"] + "|" + str(data["total_revenue"])
