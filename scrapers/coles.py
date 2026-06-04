"""Coles product scraper — extracts __NEXT_DATA__ from SSR pages."""

import argparse
import json
import os
import random
import re
import time
from html.parser import HTMLParser

import requests

from config import COLES_URL, COLES_DELAY, USER_AGENTS

# Optional proxy for Coles (they block datacenter IPs)
COLES_PROXY = os.environ.get("COLES_PROXY", "")


class NextDataParser(HTMLParser):
    """Extract __NEXT_DATA__ JSON from HTML."""

    def __init__(self):
        super().__init__()
        self.next_data = None
        self._in_script = False
        self._script_content = ""

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            attrs_dict = dict(attrs)
            if attrs_dict.get("id") == "__NEXT_DATA__":
                self._in_script = True
                self._script_content = ""

    def handle_data(self, data):
        if self._in_script:
            self._script_content += data

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script:
            self._in_script = False
            try:
                self.next_data = json.loads(self._script_content)
            except json.JSONDecodeError:
                pass


def search(query, page=1):
    """Search Coles for products. Returns list of product dicts."""
    params = {
        "q": query,
        "page": page,
    }

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-AU",
        "Referer": "https://www.coles.com.au/",
    }

    # Use proxy relay if configured (bypasses Incapsula WAF from datacenter IPs)
    if COLES_PROXY:
        # COLES_PROXY is the base URL of the proxy relay (e.g. http://lappy:8099)
        resp = requests.get(
            f"{COLES_PROXY}/",
            params=params,
            headers={"User-Agent": "TrolleySnipe"},
            timeout=20,
        )
    else:
        resp = requests.get(COLES_URL, params=params, headers=headers, timeout=20)
    resp.raise_for_status()

    # Check for Incapsula/Cloudflare block page
    if len(resp.text) < 5000 or "Incapsula" in resp.text or "ewelcome" in resp.text:
        return []

    # Parse __NEXT_DATA__
    parser = NextDataParser()
    parser.feed(resp.text)

    if not parser.next_data:
        return []

    return _extract_products(parser.next_data)


def _extract_products(next_data):
    """Extract products from __NEXT_DATA__ JSON structure."""
    products = []

    try:
        props = next_data.get("props", {})
        page_props = props.get("pageProps", {})

        # Coles structure: pageProps.searchResults.results
        search_data = page_props.get("searchResults", {})
        if isinstance(search_data, dict):
            results = search_data.get("results", [])
        else:
            results = []

        if not results:
            # Fallback paths
            results = page_props.get("products", [])
        if not results:
            content = page_props.get("content", {})
            if isinstance(content, dict):
                results = content.get("products", [])

        if not results and isinstance(page_props, dict):
            # Deep search as last resort
            for key, val in page_props.items():
                if isinstance(val, dict):
                    for k2, v2 in val.items():
                        if isinstance(v2, list) and len(v2) > 0 and isinstance(v2[0], dict):
                            results = v2
                            break
                if results:
                    break

        for item in results:
            p = _parse_product(item)
            if p:
                products.append(p)

    except Exception as e:
        print(f"Error extracting products: {e}")

    return products


def _parse_product(item):
    """Parse a single Coles product from the data."""
    if not item or not isinstance(item, dict):
        return None

    # Try to get product ID
    product_id = ""
    for id_key in ["id", "productId", "articleNumber", "sku"]:
        if item.get(id_key):
            product_id = str(item[id_key])
            break
    if not product_id:
        return None

    # Name
    name = ""
    for name_key in ["name", "title", "fullName", "displayName", "productName"]:
        if item.get(name_key):
            name = str(item[name_key]).strip()
            break
    if not name:
        return None

    # Brand
    brand = ""
    for brand_key in ["brand", "brandName", "manufacturer"]:
        if item.get(brand_key):
            brand = str(item[brand_key]).strip()
            break

    # Price — Coles uses "pricing" object
    price = 0
    was_price = 0
    is_special = 0

    pricing = item.get("pricing", {}) or {}
    if isinstance(pricing, dict):
        price = float(pricing.get("now", 0) or 0)
        was_price = float(pricing.get("was", 0) or 0)
        if pricing.get("onlineSpecial"):
            is_special = 1
    # Fallback flat fields
    if not price:
        price = float(item.get("price", 0) or 0)
    if not was_price:
        was_price = float(item.get("was_price", 0) or 0)

    # Unit price — nested in pricing.unit
    unit_price = 0
    unit_label = ""
    unit_obj = pricing.get("unit", {}) if pricing else {}
    if isinstance(unit_obj, dict):
        unit_price = float(unit_obj.get("price", 0) or 0)
        if unit_price:
            measure = unit_obj.get("ofMeasureUnits", "")
            qty = unit_obj.get("ofMeasureQuantity", 1)
            if measure:
                unit_label = f"${unit_price:.2f} / {qty}{measure}"
    # Fallback
    if not unit_label and pricing.get("comparable"):
        unit_label = pricing["comparable"]

    # Image — Coles uses "imageUris" array
    image_url = ""
    image_uris = item.get("imageUris", [])
    if isinstance(image_uris, list) and image_uris:
        uri = image_uris[0].get("uri", "") if isinstance(image_uris[0], dict) else str(image_uris[0])
        if uri:
            if uri.startswith("http"):
                image_url = uri
            elif uri.startswith("/"):
                image_url = "https://productimages.coles.com.au" + uri
            else:
                image_url = f"https://productimages.coles.com.au/{item.get('id', '')}.jpg"

    # Size
    size = str(item.get("size", "")) or ""

    # Barcode
    barcode = str(item.get("barcode", "") or "")

    # Category — from onlineHeirs or merchandiseHeir
    category = ""
    online_heirs = item.get("onlineHeirs", [])
    if isinstance(online_heirs, list) and online_heirs:
        category = online_heirs[0].get("category", "") or online_heirs[0].get("aisle", "")
    if not category:
        merch = item.get("merchandiseHeir", {})
        if isinstance(merch, dict):
            category = merch.get("categoryGroup", "") or merch.get("category", "")

    # Availability
    available = 1
    avail = item.get("availability", True)
    if isinstance(avail, bool):
        available = 1 if avail else 0
    elif isinstance(avail, str):
        available = 0 if avail.lower() in ("no", "false", "out", "unavailable") else 1

    return {
        "name": name,
        "brand": brand,
        "barcode": barcode,
        "product_id": product_id,
        "price": round(price, 2),
        "was_price": round(was_price, 2),
        "unit_price": round(unit_price, 2),
        "unit_label": unit_label,
        "image_url": image_url,
        "is_special": is_special,
        "size": size,
        "available": available,
        "category": category,
    }


def search_all_pages(query, max_pages=3):
    """Search across multiple pages. Returns all products."""
    all_products = []
    for page in range(1, max_pages + 1):
        products = search(query, page=page)
        if not products:
            break
        all_products.extend(products)
        if page < max_pages:
            time.sleep(COLES_DELAY + random.uniform(0, 1))
    return all_products


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coles product scraper")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--raw", action="store_true", help="Output raw __NEXT_DATA__")
    args = parser.parse_args()

    if args.raw:
        resp = requests.get(COLES_URL, params={"q": args.query},
                           headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=20)
        parser_nd = NextDataParser()
        parser_nd.feed(resp.text)
        if parser_nd.next_data:
            print(json.dumps(parser_nd.next_data, indent=2, default=str)[:5000])
        else:
            print("No __NEXT_DATA__ found in page")
    else:
        results = search_all_pages(args.query, max_pages=args.pages)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} products for '{args.query}':")
            for p in results[:10]:
                price_str = f"${p['price']:.2f}"
                if p["was_price"] > 0:
                    price_str += f" (was ${p['was_price']:.2f})"
                if p["unit_label"]:
                    price_str += f" — {p['unit_label']}"
                print(f"  {p['name']} | {price_str} | {p['product_id']}")
