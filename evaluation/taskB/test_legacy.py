"""特征测试：锁定 process_orders 当前行为。重构前后都必须全绿。"""
import pytest
from legacy import process_orders, format_report


def base_config(**kw):
    c = {
        "currency": "USD",
        "tax_rate": 0.1,
        "discount_threshold": 100,
        "vip_customers": ["vip1", "vip2"],
        "blacklist_skus": ["BAD1"],
    }
    c.update(kw)
    return c


def test_empty():
    out = process_orders([], base_config())
    assert out["results"] == []
    assert out["count"] == 0
    assert out["total_revenue"] == 0.0
    assert out["top_customer"] is None
    assert out["summary"] == ""


def test_single_simple():
    orders = [{"id": 1, "customer_id": "c1", "amount": 50, "status": "ok"}]
    out = process_orders(orders, base_config())
    assert out["count"] == 1
    assert out["results"][0]["id"] == 1
    # amount 50 <= threshold/2(50)? 50>50 False, 50>100 False -> discount 0
    assert out["results"][0]["discount"] == 0.0
    assert out["results"][0]["subtotal"] == 50.0
    assert out["results"][0]["tax"] == 5.0
    assert out["results"][0]["final"] == 55.0


def test_cancelled_skipped():
    orders = [{"id": 1, "customer_id": "c1", "amount": 50, "status": "cancelled"}]
    out = process_orders(orders, base_config())
    assert out["count"] == 0
    assert out["skipped"] == 1


def test_missing_field_skipped():
    orders = [{"id": 1, "customer_id": "c1"}]  # no amount/status
    out = process_orders(orders, base_config())
    assert out["skipped"] == 1
    assert out["count"] == 0


def test_none_amount_skipped():
    orders = [{"id": 1, "customer_id": "c1", "amount": None, "status": "ok"}]
    out = process_orders(orders, base_config())
    assert out["skipped"] == 1


def test_vip_discount():
    orders = [{"id": 1, "customer_id": "vip1", "amount": 50, "status": "ok"}]
    out = process_orders(orders, base_config())
    r = out["results"][0]
    assert r["is_vip"] is True
    # vip_discount = (50 - 0) * 0.03 = 1.5 ; subtotal = 50 - 0 - 1.5 - 0 = 48.5
    assert r["subtotal"] == 48.5
    assert out["vip_total"] == 50.0


def test_tag_promo():
    orders = [{"id": 1, "customer_id": "c1", "amount": 50, "status": "ok", "tags": ["SUMMER", "WINTER"]}]
    out = process_orders(orders, base_config())
    # promo = 5 + 3 = 8 ; subtotal = 50 - 8 = 42
    assert out["results"][0]["subtotal"] == 42.0


def test_items_blacklist():
    orders = [{
        "id": 1, "customer_id": "c1", "amount": 50, "status": "ok",
        "items": [{"sku": "OK", "price": 10, "qty": 2}, {"sku": "BAD1", "price": 100, "qty": 1}],
    }]
    out = process_orders(orders, base_config())
    # BAD1 blocked; item_total = 20 ; subtotal = 50 + 20 = 70
    assert out["results"][0]["subtotal"] == 70.0


def test_top_customer_and_totals():
    orders = [
        {"id": 1, "customer_id": "c1", "amount": 50, "status": "ok"},
        {"id": 2, "customer_id": "c2", "amount": 200, "status": "ok"},
        {"id": 3, "customer_id": "c1", "amount": 60, "status": "ok"},
    ]
    out = process_orders(orders, base_config())
    assert out["top_customer"] == "c2"
    assert set(out["customer_totals"].keys()) == {"c1", "c2"}
    assert out["count"] == 3


def test_summary_format():
    orders = [{"id": 7, "customer_id": "c1", "amount": 50, "status": "ok"}]
    out = process_orders(orders, base_config(currency="EUR"))
    assert out["summary"] == "order 7 cust c1 final 55.0 EUR;"
    assert out["currency"] == "EUR"


def test_format_report():
    orders = [{"id": 1, "customer_id": "c1", "amount": 50, "status": "ok"}]
    out = process_orders(orders, base_config())
    assert format_report(out, False) == "order 1 cust c1 final 55.0 USD;|55.0"
    assert "=== REPORT ===" in format_report(out, True)


def test_tier_discounts():
    orders = [
        {"id": 1, "customer_id": "c1", "amount": 150, "status": "ok"},  # >100 -> 10%
        {"id": 2, "customer_id": "c2", "amount": 75, "status": "ok"},   # >50 -> 5%
    ]
    out = process_orders(orders, base_config())
    assert out["results"][0]["discount"] == 15.0
    assert out["results"][1]["discount"] == 3.75


def test_stats_consistency():
    orders = [
        {"id": 1, "customer_id": "c1", "amount": 50, "status": "ok"},
        {"id": 2, "customer_id": "c2", "amount": 50, "status": "cancelled"},
    ]
    out = process_orders(orders, base_config())
    assert out["count"] == 1
    assert out["skipped"] == 1
