"""Cross-store product matching logic."""

from difflib import SequenceMatcher


def match_by_barcode(products_coles, products_ww):
    """Match products by barcode. Returns list of (coles_product, ww_product) tuples."""
    matches = []

    # Index Woolworths by barcode
    ww_by_barcode = {}
    for p in products_ww:
        bc = p.get("barcode", "").strip()
        if bc:
            ww_by_barcode[bc] = p

    for cp in products_coles:
        bc = cp.get("barcode", "").strip()
        if bc and bc in ww_by_barcode:
            matches.append((cp, ww_by_barcode[bc]))

    return matches


def match_by_name(products_coles, products_ww, threshold=0.75):
    """Fuzzy match products by name when no barcode match exists.
    Returns list of (coles_product, ww_product, score) tuples."""

    matches = []

    # Get names for quick pre-filter
    ww_names = [p.get("name", "") for p in products_ww]
    ww_brands = {p.get("name", ""): p.get("brand", "") for p in products_ww}

    for cp in products_coles:
        best_match = None
        best_score = 0

        cp_name = cp.get("name", "")
        cp_brand = cp.get("brand", "")
        cp_size = cp.get("size", "")

        for wp in products_ww:
            wp_name = wp.get("name", "")
            wp_brand = wp.get("brand", "")

            # Brand must match (if both have brands)
            if cp_brand and wp_brand:
                brand_sim = _similarity(cp_brand.lower(), wp_brand.lower())
                if brand_sim < 0.7:
                    continue

            # Name similarity
            score = _similarity(cp_name.lower(), wp_name.lower())

            # Boost for size match
            if cp_size and cp_size in wp_name:
                score = min(score + 0.05, 1.0)

            if score > best_score:
                best_score = score
                best_match = wp

        if best_match and best_score >= threshold:
            matches.append((cp, best_match, best_score))

    return matches


def _similarity(a, b):
    """Calculate string similarity using SequenceMatcher."""
    return SequenceMatcher(None, a, b).ratio()


def find_cheapest(products_with_prices):
    """Given a list of products with price data, determine which store is cheaper.
    Returns dict with 'cheaper' (store name), 'coles_price', 'ww_price', 'saving'."""
    result = {
        "cheaper": None,
        "coles_price": None,
        "ww_price": None,
        "saving": 0,
        "saving_pct": 0,
    }

    cp = products_with_prices.get("coles_price")
    wp = products_with_prices.get("ww_price")

    if cp and wp:
        result["coles_price"] = cp
        result["ww_price"] = wp
        if cp < wp:
            result["cheaper"] = "coles"
            result["saving"] = round(wp - cp, 2)
            result["saving_pct"] = round((wp - cp) / wp * 100, 1) if wp > 0 else 0
        elif wp < cp:
            result["cheaper"] = "woolworths"
            result["saving"] = round(cp - wp, 2)
            result["saving_pct"] = round((cp - wp) / cp * 100, 1) if cp > 0 else 0
        else:
            result["cheaper"] = "same"

    return result
