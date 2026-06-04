"""TrolleySnipe configuration."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "trolleysnipe.db")

# Scraper settings
WOOLWORTHS_URL = "https://www.woolworths.com.au/apis/ui/Search/products"
COLES_URL = "https://www.coles.com.au/search/products"
COLES_GRAPHQL_URL = "https://www.coles.com.au/api/graphql"

# Rate limiting
WOOLWORTHS_DELAY = 2.0  # seconds between requests
COLES_DELAY = 3.0  # seconds between page loads

# Search defaults
DEFAULT_PAGE_SIZE = 24
MAX_RESULTS = 60

# User agent rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

# Scheduler
DAILY_REFRESH_HOUR = 2  # 2 AM
WEEKLY_FULL_SCRAPE_DAY = "monday"

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "trolleysnipe-dev-key")
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
PORT = int(os.environ.get("PORT", 5000))
