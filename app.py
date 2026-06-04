"""TrolleySnipe — Coles vs Woolworths grocery price comparison."""

import json
import random
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from config import DEBUG, PORT, SECRET_KEY
from models import (
    cache_search,
    get_cached_search,
    get_categories,
    get_deals,
    get_latest_price,
    get_price_history,
    get_product_by_id,
    get_products_with_prices,
    get_db,
    init_db,
    insert_price,
    search_products,
    upsert_product,
)
from scrapers.coles import search as coles_search
from scrapers.woolworths import search as woolworths_search
from scrapers import match_by_barcode, match_by_name, find_cheapest

app = Flask(__name__)
app.secret_key = SECRET_KEY

# --- Page routes ---

@app.route("/")
def index():
    deals = get_deals(limit=12)
    categories = get_categories()
    return render_template("index.html", deals=deals, categories=categories)


@app.route("/search")
def search_page():
    q = request.args.get("q", "")
    return render_template("search.html", query=q)


@app.route("/deals")
def deals_page():
    deals = get_deals(limit=50)
    return render_template("deals.html", deals=deals)


@app.route("/product/<int:pid>")
def product_page(pid):
    product = get_product_by_id(pid)
    if not product:
        return render_template("search.html", query="", error="Product not found"), 404
    history = get_price_history(pid, days=30)
    coles_price = get_latest_price(pid, "coles")
    ww_price = get_latest_price(pid, "woolworths")

    comparison = find_cheapest({
        "coles_price": coles_price["price"] if coles_price else None,
        "ww_price": ww_price["price"] if ww_price else None,
    })

    return render_template("product.html",
                          product=product, history=history,
                          coles_price=coles_price, ww_price=ww_price,
                          comparison=comparison)


@app.route("/category/<cat>")
def category_page(cat):
    products = get_products_with_prices(limit=60, category=cat)
    return render_template("category.html", category=cat, products=products)


# --- API routes ---

@app.route("/api/search")
def api_search():
    """Search both stores and return matched products."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query required", "products": []})

    limit = min(request.args.get("limit", 30, type=int), 60)

    # Check DB cache first
    cached_coles = get_cached_search(q, "coles")
    cached_ww = get_cached_search(q, "woolworths")

    coles_results = json.loads(cached_coles) if cached_coles else None
    ww_results = json.loads(cached_ww) if cached_ww else None

    # Fetch from stores if no cache
    if coles_results is None:
        try:
            coles_results = coles_search(q)
            cache_search(q, "coles", json.dumps(coles_results))
        except Exception as e:
            coles_results = []
            print(f"Coles search error: {e}")

    if ww_results is None:
        try:
            ww_results = woolworths_search(q)
            cache_search(q, "woolworths", json.dumps(ww_results))
            time.sleep(1)  # polite delay
        except Exception as e:
            ww_results = []
            print(f"Woolworths search error: {e}")

    # Store products in DB
    for cp in coles_results:
        pid = upsert_product(
            name=cp["name"], coles_id=cp.get("product_id"),
            brand=cp.get("brand", ""), category=cp.get("category", ""),
            image_url=cp.get("image_url", ""), size=cp.get("size", ""),
        )
        if cp.get("price"):
            insert_price(
                product_id=pid, store="coles",
                price=cp["price"], was_price=cp.get("was_price", 0),
                unit_price=cp.get("unit_price", 0),
                unit_label=cp.get("unit_label", ""),
                is_special=cp.get("is_special", 0),
                available=cp.get("available", 1),
            )

    for wp in ww_results:
        pid = upsert_product(
            name=wp["name"], woolworths_id=wp.get("stockcode"),
            brand=wp.get("brand", ""), category=wp.get("category", ""),
            image_url=wp.get("image_url", ""), size=wp.get("size", ""),
        )
        if wp.get("price"):
            insert_price(
                product_id=pid, store="woolworths",
                price=wp["price"], was_price=wp.get("was_price", 0),
                unit_price=wp.get("unit_price", 0),
                unit_label=wp.get("unit_label", ""),
                is_special=wp.get("is_special", 0),
                available=wp.get("available", 1),
            )

    # Try barcode matching
    barcode_matches = match_by_barcode(coles_results, ww_results)
    matched_products = []

    # Build matched product dicts
    matched_ww_ids = set()
    matched_coles_ids = set()

    for cp, wp in barcode_matches:
        # Find or create unified product
        pid = upsert_product(
            name=cp["name"], coles_id=cp.get("product_id"),
            woolworths_id=wp.get("stockcode"), barcode=cp.get("barcode") or wp.get("barcode"),
            brand=cp.get("brand", "") or wp.get("brand", ""),
            category=cp.get("category", "") or wp.get("category", ""),
            image_url=cp.get("image_url", "") or wp.get("image_url", ""),
            size=cp.get("size", "") or wp.get("size", ""),
        )
        product = get_product_by_id(pid)
        if product:
            comparison = find_cheapest({
                "coles_price": cp.get("price"),
                "ww_price": wp.get("price"),
            })
            matched_products.append({
                "id": pid,
                "name": product["name"],
                "brand": product["brand"],
                "image_url": product["image_url"],
                "category": product["category"],
                "coles": {
                    "price": cp.get("price"),
                    "was_price": cp.get("was_price"),
                    "unit_price": cp.get("unit_price"),
                    "unit_label": cp.get("unit_label"),
                    "is_special": cp.get("is_special", 0),
                    "available": cp.get("available", 1),
                },
                "woolworths": {
                    "price": wp.get("price"),
                    "was_price": wp.get("was_price"),
                    "unit_price": wp.get("unit_price"),
                    "unit_label": wp.get("unit_label"),
                    "is_special": wp.get("is_special", 0),
                    "available": wp.get("available", 1),
                },
                "comparison": comparison,
            })
            matched_ww_ids.add(wp.get("stockcode"))
            matched_coles_ids.add(cp.get("product_id"))

    # Fuzzy match remaining unmatched products
    unmatched_coles = [p for p in coles_results if p.get("product_id") not in matched_coles_ids]
    unmatched_ww = [p for p in ww_results if p.get("stockcode") not in matched_ww_ids]

    if unmatched_coles and unmatched_ww:
        fuzzy_matches = match_by_name(unmatched_coles, unmatched_ww, threshold=0.65)
        for cp, wp, score in fuzzy_matches:
            comparison = find_cheapest({
                "coles_price": cp.get("price"),
                "ww_price": wp.get("price"),
            })
            matched_products.append({
                "name": cp.get("name", ""),
                "brand": cp.get("brand", ""),
                "image_url": cp.get("image_url", ""),
                "coles": {
                    "price": cp.get("price"),
                    "was_price": cp.get("was_price"),
                    "unit_price": cp.get("unit_price"),
                    "unit_label": cp.get("unit_label"),
                    "is_special": cp.get("is_special", 0),
                    "available": cp.get("available", 1),
                },
                "woolworths": {
                    "price": wp.get("price"),
                    "was_price": wp.get("was_price"),
                    "unit_price": wp.get("unit_price"),
                    "unit_label": wp.get("unit_label"),
                    "is_special": wp.get("is_special", 0),
                    "available": wp.get("available", 1),
                },
                "comparison": comparison,
                "match_score": round(score, 2),
            })

    # Sort by savings (biggest first)
    matched_products.sort(
        key=lambda x: x["comparison"].get("saving", 0), reverse=True
    )

    return jsonify({
        "query": q,
        "total_matched": len(matched_products),
        "coles_total": len(coles_results),
        "woolworths_total": len(ww_results),
        "products": matched_products[:limit],
    })


@app.route("/api/product/<int:pid>")
def api_product(pid):
    """Get a single product with price history."""
    product = get_product_by_id(pid)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    coles_price = get_latest_price(pid, "coles")
    ww_price = get_latest_price(pid, "woolworths")
    history = get_price_history(pid, days=30)

    comparison = find_cheapest({
        "coles_price": coles_price["price"] if coles_price else None,
        "ww_price": ww_price["price"] if ww_price else None,
    })

    return jsonify({
        "product": dict(product),
        "coles_price": dict(coles_price) if coles_price else None,
        "woolworths_price": dict(ww_price) if ww_price else None,
        "comparison": comparison,
        "history": [dict(h) for h in history],
    })


@app.route("/api/compare/<int:pid>")
def api_compare(pid):
    """Side-by-side comparison for a product."""
    product = get_product_by_id(pid)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    coles_price = get_latest_price(pid, "coles")
    ww_price = get_latest_price(pid, "woolworths")

    comparison = find_cheapest({
        "coles_price": coles_price["price"] if coles_price else None,
        "ww_price": ww_price["price"] if ww_price else None,
    })

    return jsonify({
        "product": dict(product),
        "coles": {
            "price": coles_price["price"] if coles_price else None,
            "was_price": coles_price["was_price"] if coles_price else None,
            "unit_price": coles_price["unit_price"] if coles_price else None,
            "unit_label": coles_price["unit_label"] if coles_price else None,
            "is_special": coles_price["is_special"] if coles_price else 0,
        },
        "woolworths": {
            "price": ww_price["price"] if ww_price else None,
            "was_price": ww_price["was_price"] if ww_price else None,
            "unit_price": ww_price["unit_price"] if ww_price else None,
            "unit_label": ww_price["unit_label"] if ww_price else None,
            "is_special": ww_price["is_special"] if ww_price else 0,
        },
        "comparison": comparison,
    })


@app.route("/api/categories")
def api_categories():
    """List product categories."""
    cats = get_categories()
    return jsonify({"categories": [dict(c) for c in cats]})


@app.route("/api/deals")
def api_deals():
    """Products currently on special."""
    deals = get_deals(limit=50)
    result = []
    for d in deals:
        comparison = find_cheapest({
            "coles_price": d.get("coles_price"),
            "ww_price": d.get("ww_price"),
        })
        result.append({**dict(d), "comparison": comparison})
    return jsonify({"deals": result})


@app.route("/api/cheapest")
def api_cheapest():
    """Products that are cheaper at a specific store."""
    store = request.args.get("store", "coles")
    limit = min(request.args.get("limit", 30, type=int), 60)

    if store not in ("coles", "woolworths"):
        return jsonify({"error": "store must be 'coles' or 'woolworths'"}), 400

    products = get_products_with_prices(limit=limit, store_sort=store)
    result = []
    for p in products:
        comparison = find_cheapest({
            "coles_price": p.get("coles_price"),
            "ww_price": p.get("ww_price"),
        })
        result.append({**dict(p), "comparison": comparison})

    return jsonify({
        "store": store,
        "products": result,
    })


@app.route("/api/history/<int:pid>")
def api_history(pid):
    """Price history for a product."""
    days = request.args.get("days", 30, type=int)
    history = get_price_history(pid, days=days)
    return jsonify({
        "product_id": pid,
        "days": days,
        "history": [dict(h) for h in history],
    })


# --- Health check ---

@app.route("/api/health")
def api_health():
    """Health check endpoint."""
    with get_db() as conn:
        product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        price_count = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]

    return jsonify({
        "status": "ok",
        "product_count": product_count,
        "price_count": price_count,
    })


# --- Context processor for templates ---

@app.context_processor
def inject_globals():
    return {
        "now": datetime.now(),
    }


# --- Init ---

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
