"""TrolleySnipe price refresh scheduler."""

import json
import random
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config import DAILY_REFRESH_HOUR, WEEKLY_FULL_SCRAPE_DAY
from models import get_db, insert_price, upsert_product, get_db
from scrapers.woolworths import search as ww_search
from scrapers.coles import search as coles_search

# Common grocery search terms for seeding / refreshing
SEED_QUERIES = [
    "milk", "bread", "eggs", "butter", "cheese", "chicken", "beef mince",
    "rice", "pasta", "sauce", "cereal", "yoghurt", "bananas", "apples",
    "potatoes", "onions", "tomatoes", "lettuce", "carrots", "toilet paper",
    "paper towels", "dishwashing liquid", "laundry detergent", "sugar",
    "flour", "oil", "coffee", "tea", "soft drink", "water", "juice",
    "frozen chips", "ice cream", "chocolate", "biscuits", "nuts",
    "tuna", "salmon", "pasta sauce", "soup", "noodles", "pizza",
    "bacon", "ham", "sausages", "lamb", "pork", "fish",
    "avocado", "broccoli", "capsicum", "mushroom", "garlic",
    "shampoo", "conditioner", "soap", "toothpaste", "nappies",
    "baby wipes", "dog food", "cat food", "milk powder",
    "almond milk", "oat milk", "sparkling water", "beer", "wine",
]


def refresh_top_products():
    """Refresh prices for common grocery items from both stores."""
    print(f"[{datetime.now()}] Starting daily price refresh...")

    success = 0
    errors = 0

    for query in SEED_QUERIES:
        try:
            # Woolworths
            try:
                ww_results = ww_search(query)
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
                time.sleep(2 + random.uniform(0, 1))
            except Exception as e:
                print(f"  Woolworths error for '{query}': {e}")
                errors += 1

            # Coles
            try:
                coles_results = coles_search(query)
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
                time.sleep(3 + random.uniform(0, 1))
            except Exception as e:
                print(f"  Coles error for '{query}': {e}")
                errors += 1

            success += 1

        except Exception as e:
            print(f"  Error refreshing '{query}': {e}")
            errors += 1

    print(f"[{datetime.now()}] Refresh complete: {success} queries, {errors} errors")


def cleanup_old_prices(days=90):
    """Remove price records older than N days to keep DB lean."""
    with get_db() as conn:
        deleted = conn.execute(
            "DELETE FROM prices WHERE checked_at < datetime('now', ?)",
            (f"-{days} days",),
        ).rowcount
    if deleted:
        print(f"[{datetime.now()}] Cleaned {deleted} old price records")


def get_scheduler():
    """Create and configure the APScheduler."""
    scheduler = BackgroundScheduler()

    # Daily price refresh
    scheduler.add_job(
        refresh_top_products,
        "cron",
        hour=DAILY_REFRESH_HOUR,
        minute=0,
        id="daily_refresh",
        name="Daily price refresh",
        replace_existing=True,
    )

    # Weekly DB cleanup
    scheduler.add_job(
        cleanup_old_prices,
        "cron",
        day_of_week="sunday",
        hour=3,
        minute=0,
        id="weekly_cleanup",
        name="Weekly DB cleanup",
        replace_existing=True,
    )

    return scheduler


if __name__ == "__main__":
    print("Running one-shot price refresh...")
    refresh_top_products()
