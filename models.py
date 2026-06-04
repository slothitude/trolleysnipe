"""TrolleySnipe database models and query helpers."""

import os
import sqlite3
import time
from contextlib import contextmanager

from config import DB_PATH, DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode TEXT,
    slug TEXT UNIQUE,
    name TEXT NOT NULL,
    coles_id TEXT,
    woolworths_id TEXT,
    brand TEXT DEFAULT '',
    category TEXT DEFAULT '',
    subcategory TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    size TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    store TEXT NOT NULL,
    price REAL NOT NULL,
    was_price REAL DEFAULT 0,
    unit_price REAL DEFAULT 0,
    unit_label TEXT DEFAULT '',
    available INTEGER DEFAULT 1,
    is_special INTEGER DEFAULT 0,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prices_product ON prices(product_id);
CREATE INDEX IF NOT EXISTS idx_prices_store ON prices(store);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(checked_at);

CREATE TABLE IF NOT EXISTS search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    store TEXT NOT NULL,
    results_json TEXT NOT NULL,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(query, store)
);
"""


def init_db():
    """Create tables if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Product queries ---

def upsert_product(name, coles_id=None, woolworths_id=None, barcode=None,
                   brand="", category="", subcategory="", image_url="", size=""):
    """Insert or update a product. Returns product ID."""
    with get_db() as conn:
        slug = _make_slug(name)
        existing = conn.execute(
            "SELECT id FROM products WHERE slug = ?", (slug,)
        ).fetchone()

        if existing:
            pid = existing["id"]
            updates = []
            params = []
            if coles_id and not woolworths_id:
                # Only update coles fields
                if coles_id:
                    updates.append("coles_id = ?")
                    params.append(coles_id)
            if woolworths_id and not coles_id:
                if woolworths_id:
                    updates.append("woolworths_id = ?")
                    params.append(woolworths_id)
            if coles_id:
                updates.append("coles_id = ?")
                params.append(coles_id)
            if woolworths_id:
                updates.append("woolworths_id = ?")
                params.append(woolworths_id)
            if barcode:
                updates.append("barcode = ?")
                params.append(barcode)
            if brand:
                updates.append("brand = ?")
                params.append(brand)
            if category:
                updates.append("category = ?")
                params.append(category)
            if image_url:
                updates.append("image_url = ?")
                params.append(image_url)
            if size:
                updates.append("size = ?")
                params.append(size)
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(pid)
            if updates:
                conn.execute(
                    f"UPDATE products SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
            return pid
        else:
            cur = conn.execute(
                """INSERT INTO products (name, slug, coles_id, woolworths_id, barcode,
                   brand, category, subcategory, image_url, size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, slug, coles_id, woolworths_id, barcode,
                 brand, category, subcategory, image_url, size),
            )
            return cur.lastrowid


def get_product_by_id(pid):
    """Get a single product by ID."""
    with get_db() as conn:
        return conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()


def search_products(query, limit=30):
    """Search products by name using FTS5-style LIKE (simple for MVP)."""
    with get_db() as conn:
        return conn.execute(
            """SELECT p.*, c.price as coles_price, c.was_price as coles_was,
                      c.unit_price as coles_unit, c.unit_label as coles_unit_label,
                      c.is_special as coles_special, c.available as coles_avail,
                      w.price as ww_price, w.was_price as ww_was,
                      w.unit_price as ww_unit, w.unit_label as ww_unit_label,
                      w.is_special as ww_special, w.available as ww_avail
               FROM products p
               LEFT JOIN (SELECT product_id, price, was_price, unit_price, unit_label,
                                 is_special, available
                          FROM prices WHERE store='coles'
                          AND checked_at = (SELECT MAX(checked_at) FROM prices p2
                                            WHERE p2.store='coles' AND p2.product_id=prices.product_id)
                         ) c ON c.product_id = p.id
               LEFT JOIN (SELECT product_id, price, was_price, unit_price, unit_label,
                                 is_special, available
                          FROM prices WHERE store='woolworths'
                          AND checked_at = (SELECT MAX(checked_at) FROM prices p3
                                            WHERE p3.store='woolworths' AND p3.product_id=prices.product_id)
                         ) w ON w.product_id = p.id
               WHERE p.name LIKE ?
               ORDER BY CASE
                   WHEN p.name LIKE ? THEN 1
                   WHEN p.name LIKE ? THEN 2
                   ELSE 3
               END
               LIMIT ?""",
            (f"%{query}%", f"{query}%", f"%{query}%", limit),
        ).fetchall()


def get_products_with_prices(limit=50, offset=0, category=None, store_sort=None):
    """Get products with latest prices from both stores."""
    with get_db() as conn:
        sql = """SELECT p.*, c.price as coles_price, c.was_price as coles_was,
                        c.unit_price as coles_unit, c.unit_label as coles_unit_label,
                        c.is_special as coles_special, c.available as coles_avail,
                        w.price as ww_price, w.was_price as ww_was,
                        w.unit_price as ww_unit, w.unit_label as ww_unit_label,
                        w.is_special as ww_special, w.available as ww_avail
                 FROM products p
                 LEFT JOIN (SELECT product_id, price, was_price, unit_price, unit_label,
                                   is_special, available
                            FROM prices WHERE store='coles'
                            AND checked_at = (SELECT MAX(checked_at) FROM prices p2
                                              WHERE p2.store='coles' AND p2.product_id=prices.product_id)
                           ) c ON c.product_id = p.id
                 LEFT JOIN (SELECT product_id, price, was_price, unit_price, unit_label,
                                   is_special, available
                            FROM prices WHERE store='woolworths'
                            AND checked_at = (SELECT MAX(checked_at) FROM prices p3
                                              WHERE p3.store='woolworths' AND p3.product_id=prices.product_id)
                           ) w ON w.product_id = p.id
                 """
        params = []
        if category:
            sql += " WHERE p.category = ?"
            params.append(category)

        if store_sort == "coles":
            sql += " ORDER BY c.price ASC"
        elif store_sort == "woolworths":
            sql += " ORDER BY w.price ASC"
        elif store_sort == "savings":
            sql += " ORDER BY ABS(c.price - w.price) DESC"
        else:
            sql += " ORDER BY p.updated_at DESC"

        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return conn.execute(sql, params).fetchall()


def get_deals(limit=30):
    """Get products currently on special at either store."""
    with get_db() as conn:
        return conn.execute(
            """SELECT p.*, c.price as coles_price, c.was_price as coles_was,
                      c.unit_price as coles_unit, c.unit_label as coles_unit_label,
                      c.is_special as coles_special,
                      w.price as ww_price, w.was_price as ww_was,
                      w.unit_price as ww_unit, w.unit_label as ww_unit_label,
                      w.is_special as ww_special
               FROM products p
               LEFT JOIN (SELECT product_id, price, was_price, unit_price, unit_label,
                                 is_special
                          FROM prices WHERE store='coles'
                          AND checked_at = (SELECT MAX(checked_at) FROM prices p2
                                            WHERE p2.store='coles' AND p2.product_id=prices.product_id)
                         ) c ON c.product_id = p.id
               LEFT JOIN (SELECT product_id, price, was_price, unit_price, unit_label,
                                 is_special
                          FROM prices WHERE store='woolworths'
                          AND checked_at = (SELECT MAX(checked_at) FROM prices p3
                                            WHERE p3.store='woolworths' AND p3.product_id=prices.product_id)
                         ) w ON w.product_id = p.id
               WHERE c.is_special = 1 OR w.is_special = 1
               ORDER BY ((CASE WHEN c.was_price > 0 THEN c.was_price - c.price ELSE 0 END) +
                         (CASE WHEN w.was_price > 0 THEN w.was_price - w.price ELSE 0 END)) DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()


def get_price_history(product_id, days=30):
    """Get price history for a product."""
    with get_db() as conn:
        return conn.execute(
            """SELECT store, price, was_price, unit_price, unit_label, checked_at
               FROM prices
               WHERE product_id = ? AND checked_at > datetime('now', ?)
               ORDER BY checked_at ASC""",
            (product_id, f"-{days} days"),
        ).fetchall()


def get_categories():
    """Get all product categories."""
    with get_db() as conn:
        return conn.execute(
            "SELECT category, COUNT(*) as count FROM products WHERE category != '' GROUP BY category ORDER BY count DESC"
        ).fetchall()


# --- Price queries ---

def insert_price(product_id, store, price, was_price=0, unit_price=0,
                 unit_label="", available=1, is_special=0):
    """Insert a price snapshot."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO prices (product_id, store, price, was_price, unit_price,
                                  unit_label, available, is_special)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (product_id, store, price, was_price, unit_price,
             unit_label, available, is_special),
        )


def get_latest_price(product_id, store):
    """Get the most recent price for a product at a store."""
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM prices
               WHERE product_id = ? AND store = ?
               ORDER BY checked_at DESC LIMIT 1""",
            (product_id, store),
        ).fetchone()


# --- Search cache ---

def get_cached_search(query, store, max_age_hours=1):
    """Get cached search results if fresh enough."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT results_json FROM search_cache
               WHERE query = ? AND store = ?
               AND cached_at > datetime('now', ?)""",
            (query, store, f"-{max_age_hours} hours"),
        ).fetchone()
        return row["results_json"] if row else None


def cache_search(query, store, results_json):
    """Cache search results. Replaces existing cache entry."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO search_cache (query, store, results_json)
               VALUES (?, ?, ?)
               ON CONFLICT(query, store) DO UPDATE SET
               results_json = excluded.results_json,
               cached_at = CURRENT_TIMESTAMP""",
            (query, store, results_json),
        )


# --- Helpers ---

def _make_slug(name):
    """Create URL-friendly slug from product name."""
    slug = name.lower().strip()[:80]
    for ch in '"/\\' :
        slug = slug.replace(ch, "")
    slug = slug.replace(" ", "-")
    # Remove non-alphanumeric except hyphens
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = slug.strip("-")[:60]
    if not slug:
        slug = f"product-{int(time.time())}"
    return slug
