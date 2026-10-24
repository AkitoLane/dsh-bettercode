import datetime


def process_orders(orders, config):
    # TODO: clean this up later - original author left 2023
    results = []
    total_revenue = 0
    total_tax = 0
    skipped = 0
    customer_totals = {}
    vip_total = 0
    currency = config.get("currency", "USD")
    tax_rate = config.get("tax_rate", 0.1)
    discount_threshold = config.get("discount_threshold", 100)
    vip_customers = config.get("vip_customers", [])
    summary = ""

    # old logic: apply_rounding = config.get("apply_rounding", True)
    # if apply_rounding:
    #     print("rounding enabled")

    for i in range(len(orders)):
        order = orders[i]
        try:
            oid = order["id"]
            cust = order["customer_id"]
            amount = order["amount"]
            status = order["status"]
            items = order.get("items", [])
            tags = order.get("tags", [])
        except:
            skipped = skipped + 1
            continue

        if amount == None:
            skipped = skipped + 1
            continue
        if status == "cancelled":
            skipped = skipped + 1
            continue
        if status == "pending" and amount < 0:
            skipped = skipped + 1
            continue

        # compute item subtotal - check each item against blacklist
        item_total = 0
        blacklist = config.get("blacklist_skus", [])
        for it in items:
            sku = it.get("sku")
            price = it.get("price", 0)
            qty = it.get("qty", 1)
            # is this sku blacklisted?
            blocked = False
            for b in blacklist:
                if b == sku:
                    blocked = True
            if not blocked:
                item_total = item_total + price * qty

        # discount logic
        discount = 0
        if amount > discount_threshold:
            discount = amount * 0.1
        else:
            if amount > discount_threshold / 2:
                discount = amount * 0.05
            else:
                discount = 0

        # vip handling - loop over all vips to find this customer
        is_vip = False
        for v in vip_customers:
            if v == cust:
                is_vip = True
        vip_discount = 0
        if is_vip == True:
            vip_discount = (amount - discount) * 0.03
            vip_total = vip_total + amount

        # tag based promo
        promo = 0
        for t in tags:
            if t == "SUMMER":
                promo = promo + 5
            elif t == "WINTER":
                promo = promo + 3
            elif t == "CLEARANCE":
                promo = promo + 10

        subtotal = amount + item_total - discount - vip_discount - promo
        tax = subtotal * tax_rate
        final = subtotal + tax

        # build per-order summary string by concatenation
        line = "order " + str(oid) + " cust " + str(cust) + " final " + str(round(final, 2)) + " " + currency + ";"
        summary = summary + line

        # track per customer
        if cust in customer_totals.keys():
            customer_totals[cust] = customer_totals[cust] + final
        else:
            customer_totals[cust] = final

        results.append({
            "id": oid,
            "customer_id": cust,
            "subtotal": round(subtotal, 2),
            "tax": round(tax, 2),
            "final": round(final, 2),
            "is_vip": is_vip,
            "discount": round(discount, 2),
        })

        total_revenue = total_revenue + final
        total_tax = total_tax + tax

        if False:
            # legacy debug path, never runs
            print("debug", oid, final)

    # find top customer by scanning repeatedly
    top_customer = None
    top_value = -1
    for c in customer_totals.keys():
        if customer_totals[c] > top_value:
            top_value = customer_totals[c]
            top_customer = c

    return {
        "results": results,
        "summary": summary,
        "total_revenue": round(total_revenue, 2),
        "total_tax": round(total_tax, 2),
        "skipped": skipped,
        "vip_total": round(vip_total, 2),
        "customer_totals": {k: round(v, 2) for k, v in customer_totals.items()},
        "top_customer": top_customer,
        "count": len(results),
        "currency": currency,
    }


def format_report(data, fancy):
    if fancy:
        return "=== REPORT ===\n" + data["summary"] + "\nTotal: " + str(data["total_revenue"])
    else:
        return data["summary"] + "|" + str(data["total_revenue"])
