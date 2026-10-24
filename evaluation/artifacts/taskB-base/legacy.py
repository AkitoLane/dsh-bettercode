"""Order processing pipeline.

Refactored from the original legacy script. The externally visible behavior
of ``process_orders`` and ``format_report`` is preserved exactly: same return
structure and field order, same floating-point operation/accumulation order,
same exception types for bad input, and same legacy quirks (each one is kept
on purpose and marked with a ``Legacy quirk`` comment).
"""

from typing import Any, Callable, Iterable, NamedTuple, Optional

DEFAULT_CURRENCY = "USD"
DEFAULT_TAX_RATE = 0.1
DEFAULT_DISCOUNT_THRESHOLD = 100

FULL_TIER_DISCOUNT_RATE = 0.1   # applied when amount > threshold
HALF_TIER_DISCOUNT_RATE = 0.05  # applied when amount > threshold / 2
VIP_DISCOUNT_RATE = 0.03
PROMO_VALUE_BY_TAG = {"SUMMER": 5, "WINTER": 3, "CLEARANCE": 10}

# Legacy quirk: the best-customer scan starts from -1, so a customer whose
# accumulated total is <= -1 never becomes top_customer (it stays None).
TOP_CUSTOMER_FLOOR = -1


class _OrderFields(NamedTuple):
    """The per-order fields the legacy code read up front, in the same order."""

    order_id: Any
    customer_id: Any
    amount: Any
    status: Any
    items: Any
    tags: Any


def _build_membership_test(candidates: Any) -> Callable[[Any], bool]:
    """Build a predicate matching a value against ``candidates`` by equality.

    Reproduces the legacy linear ``for candidate in candidates: if candidate ==
    value`` scans (candidate on the left, no short-circuit) while answering the
    common case in O(1): when both the members and the looked-up value are
    plain hash-stable builtins, a frozenset lookup is provably equivalent to
    the equality scan. Anything exotic (custom ``__eq__``/``__hash__``, NaN,
    one-shot iterables) falls back to the exact legacy scan. Preparation is
    lazy so a broken ``candidates`` container (e.g. ``None``) raises at the
    same moment the legacy scan would have.
    """
    prepared = False
    fast_set: Optional[frozenset] = None
    scan_source: Any = None

    def contains(value: Any) -> bool:
        nonlocal prepared, fast_set, scan_source
        if not prepared:
            prepared = True
            fast_set, scan_source = _prepare_lookup(candidates)
        if fast_set is not None and _is_hash_stable(value):
            return value in fast_set
        found = False
        for candidate in scan_source:
            if candidate == value:
                found = True  # no break: the legacy loops scanned every entry
        return found

    return contains


# Containers that can safely be materialized once and re-scanned: iterating
# them again later yields the same items, exactly like the legacy loops.
_REITERABLE_CONTAINERS = (list, tuple, set, frozenset, dict, str, bytes, bytearray, range)

# Types where hashing plus ``in`` is provably equivalent to an ``==`` scan.
# NaN floats are excluded (``nan is nan`` yet ``nan == nan`` is False, and a
# set lookup can hit the identity shortcut), as is every type that may define
# custom ``__eq__``/``__hash__``.
_HASH_STABLE_TYPES = frozenset({str, int, bool, bytes, type(None), float})


def _is_hash_stable(value: Any) -> bool:
    value_type = type(value)
    if value_type not in _HASH_STABLE_TYPES:
        return False
    return value_type is not float or value == value


def _prepare_lookup(candidates: Any):
    """Return ``(fast_set, scan_source)`` for membership tests over candidates.

    ``fast_set`` is a frozenset usable for O(1) lookups, or None when hashing
    could answer differently than the legacy equality scan. ``scan_source`` is
    what the linear fallback iterates.

    The container is never copied: the fallback walks the live object, so
    re-iteration and even mutation during the loop behave exactly as the legacy
    scans did.
    """
    if not isinstance(candidates, _REITERABLE_CONTAINERS):
        # One-shot or exotic iterable: the legacy code re-iterated it on every
        # lookup (progressively consuming generators), so hand it out live.
        return None, candidates
    for member in candidates:
        if not _is_hash_stable(member):
            return None, candidates  # custom __eq__/__hash__ or NaN member
    return frozenset(candidates), candidates


def _extract_order_fields(order: Any) -> Optional[_OrderFields]:
    """Read the required fields of one order; return None if it is malformed.

    Mirrors the legacy behavior of skipping any order whose required keys are
    missing (or that is not a mapping at all).
    """
    try:
        return _OrderFields(
            order_id=order["id"],
            customer_id=order["customer_id"],
            amount=order["amount"],
            status=order["status"],
            items=order.get("items", []),
            tags=order.get("tags", []),
        )
    except Exception:
        return None


def _is_skipped(amount: Any, status: Any) -> bool:
    """Apply the legacy skip rules, in the legacy evaluation order.

    Legacy quirk: the None check is ``amount == None`` (equality, not
    identity), so an object whose ``__eq__`` accepts None is also skipped.
    """
    if amount == None:  # noqa: E711 - deliberate equality, see docstring
        return True
    if status == "cancelled":
        return True
    return status == "pending" and amount < 0


def _sum_allowed_items(items: Iterable, is_blacklisted: Callable[[Any], bool]):
    """Sum ``price * qty`` over the items whose sku is not blacklisted."""
    item_total = 0
    for item in items:
        sku = item.get("sku")
        price = item.get("price", 0)
        qty = item.get("qty", 1)
        if not is_blacklisted(sku):
            item_total = item_total + price * qty
    return item_total


def _tier_discount(amount: Any, threshold: Any):
    """Two-tier amount discount.

    Returns int 0 (not 0.0) for the no-discount tier, exactly as the legacy
    code did, so downstream arithmetic keeps identical types.
    """
    if amount > threshold:
        return amount * FULL_TIER_DISCOUNT_RATE
    if amount > threshold / 2:
        return amount * HALF_TIER_DISCOUNT_RATE
    return 0


def _sum_promotions(tags: Iterable):
    """Add up the fixed promo value of every recognized tag.

    Plain str tags take a dict lookup. Anything else (objects with custom
    ``__eq__``) falls back to the legacy ordered equality scan, where the tag
    is on the left of ``==`` and the first matching name wins.
    """
    promo = 0
    for tag in tags:
        if type(tag) is str:
            promo += PROMO_VALUE_BY_TAG.get(tag, 0)
            continue
        for name, value in PROMO_VALUE_BY_TAG.items():
            if tag == name:
                promo += value
                break
    return promo


def _format_summary_line(order_id: Any, customer_id: Any, final: float, currency: Any) -> str:
    return (
        "order " + str(order_id)
        + " cust " + str(customer_id)
        + " final " + str(round(final, 2))
        + " " + currency + ";"
    )


def _find_top_customer(customer_totals: dict):
    """Customer with the strictly greatest total; ties keep the earliest one."""
    top_customer = None
    top_value = TOP_CUSTOMER_FLOOR
    for customer, total in customer_totals.items():
        if total > top_value:
            top_value = total
            top_customer = customer
    return top_customer


def process_orders(orders: list[dict], config: dict) -> dict:
    currency = config.get("currency", DEFAULT_CURRENCY)
    tax_rate = config.get("tax_rate", DEFAULT_TAX_RATE)
    discount_threshold = config.get("discount_threshold", DEFAULT_DISCOUNT_THRESHOLD)
    is_blacklisted = _build_membership_test(config.get("blacklist_skus", []))
    is_vip_customer = _build_membership_test(config.get("vip_customers", []))

    results = []
    summary_parts = []
    customer_totals = {}
    total_revenue = 0
    total_tax = 0
    vip_total = 0
    skipped = 0

    # Legacy quirk: orders is walked by index (len + __getitem__), not via the
    # iterator protocol. Kept on purpose so non-list sized containers and
    # subscript failures behave exactly as the original code did.
    for index in range(len(orders)):
        order = orders[index]
        fields = _extract_order_fields(order)
        if fields is None:
            skipped += 1
            continue
        if _is_skipped(fields.amount, fields.status):
            skipped += 1
            continue

        amount = fields.amount
        customer_id = fields.customer_id

        item_total = _sum_allowed_items(fields.items, is_blacklisted)
        discount = _tier_discount(amount, discount_threshold)

        is_vip = is_vip_customer(customer_id)
        vip_discount = 0
        if is_vip:
            vip_discount = (amount - discount) * VIP_DISCOUNT_RATE
            vip_total = vip_total + amount

        promo = _sum_promotions(fields.tags)

        subtotal = amount + item_total - discount - vip_discount - promo
        tax = subtotal * tax_rate
        final = subtotal + tax

        summary_parts.append(
            _format_summary_line(fields.order_id, customer_id, final, currency)
        )

        if customer_id in customer_totals:
            customer_totals[customer_id] = customer_totals[customer_id] + final
        else:
            customer_totals[customer_id] = final

        results.append({
            "id": fields.order_id,
            "customer_id": customer_id,
            "subtotal": round(subtotal, 2),
            "tax": round(tax, 2),
            "final": round(final, 2),
            "is_vip": is_vip,
            "discount": round(discount, 2),
        })

        total_revenue = total_revenue + final
        total_tax = total_tax + tax

    return {
        "results": results,
        "summary": "".join(summary_parts),
        "total_revenue": round(total_revenue, 2),
        "total_tax": round(total_tax, 2),
        "skipped": skipped,
        "vip_total": round(vip_total, 2),
        "customer_totals": {c: round(v, 2) for c, v in customer_totals.items()},
        "top_customer": _find_top_customer(customer_totals),
        "count": len(results),
        "currency": currency,
    }


def format_report(data, fancy):
    if fancy:
        return "=== REPORT ===\n" + data["summary"] + "\nTotal: " + str(data["total_revenue"])
    return data["summary"] + "|" + str(data["total_revenue"])
