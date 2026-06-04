"""Woolworths product scraper — uses their public Search API."""

import argparse
import json
import random
import time
import urllib.parse

import requests

from config import WOOLWORTHS_URL, WOOLWORTHS_DELAY, USER_AGENTS, DEFAULT_PAGE_SIZE


def search(query, page_number=1, page_size=DEFAULT_PAGE_SIZE):
    """Search Woolworths for products. Returns list of product dicts."""
    params = {
        "searchTerm": query,
        "pageNumber": page_number,
        "pageSize": page_size,
        "filters": [],
        "sortType": "RELEVANCE",
        "location": "/shop/store/4854",  # Generic NSW store
        "isSpecialOnly": False,
        "availability": True,
    }

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "en-AU",
        "Referer": "https://www.woolworths.com.au/",
    }

    resp = requests.get(WOOLWORTHS_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    products = []
    for item in data.get("Products", []):
        # Woolworths nests Products inside each group — unwrap
        inner = item.get("Products", [])
        if isinstance(inner, list):
            for sub in inner:
                p = _parse_product(sub)
                if p:
                    products.append(p)
        else:
            p = _parse_product(item)
            if p:
                products.append(p)

    return products


def _parse_product(item):
    """Parse a single Woolworths product from API response."""
    if not item or not item.get("Name"):
        return None

    # Price — direct fields on the product object
    price = float(item.get("Price", 0) or 0)
    was_price = float(item.get("WasPrice", 0) or 0)
    is_special = 1 if item.get("IsOnSpecial") else 0

    # Unit (cup) price
    unit_price = float(item.get("CupPrice", 0) or 0)
    unit_label = item.get("CupString", "")

    # Image
    image_url = (item.get("LargeImageFile") or
                 item.get("MediumImageFile") or
                 item.get("SmallImageFile") or "")

    # Barcode
    barcode = str(item.get("Barcode", "") or "")

    # Stockcode
    stockcode = str(item.get("Stockcode", ""))

    # Brand and name cleanup
    name = item.get("Name", "").strip()
    brand = item.get("Brand", "") or ""
    # Remove brand prefix from name if duplicated
    if brand and name.lower().startswith(brand.lower()):
        name = name[len(brand):].strip()

    return {
        "name": name,
        "brand": brand,
        "barcode": barcode,
        "stockcode": stockcode,
        "price": round(price, 2),
        "was_price": round(was_price, 2),
        "unit_price": round(unit_price, 2),
        "unit_label": unit_label,
        "image_url": image_url,
        "is_special": is_special,
        "size": item.get("PackageSize", ""),
        "available": 1 if item.get("IsInStock", True) else 0,
        "category": item.get("SecondaryCategoryName", "") or item.get("CategoryName", ""),
    }


def search_all_pages(query, max_pages=3):
    """Search across multiple pages. Returns all products."""
    all_products = []
    for page in range(1, max_pages + 1):
        products = search(query, page_number=page)
        if not products:
            break
        all_products.extend(products)
        if page < max_pages:
            time.sleep(WOOLWORTHS_DELAY + random.uniform(0, 0.5))
    return all_products


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Woolworths product scraper")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

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
            print(f"  {p['name']} | {price_str} | {p['stockcode']}")
