# TrolleySnipe

Coles vs Woolworths grocery price comparison. Find out who's cheaper, track specials, and never overpay on groceries again.

## Features

- **Dual-store search** — queries Coles and Woolworths simultaneously
- **Product matching** — barcode matching + fuzzy name matching across stores
- **Price comparison** — shows which store is cheaper and by how much
- **Price history** — 30-day price tracking per product
- **Deals page** — products currently on special at either store
- **Scheduled refresh** — automatic daily price updates + weekly full scrape
- **Unit pricing** — compare per-100g/ml prices for fair comparisons

## Architecture

```
                    ┌─────────────┐
  User ──────────►  │  Flask App   │  (Oracle Docker, port 5010)
                    │  app.py      │
                    └──┬──────┬───┘
                       │      │
              ┌────────┘      └────────┐
              ▼                       ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ Woolworths API   │    │ Coles Proxy       │
    │ (JSON API)       │    │ (Lappy, port 8099)│
    │ scrapers/ww.py   │    │ coles_proxy.py    │
    └──────────────────┘    └────────┬─────────┘
                                     │
                                     ▼
                            ┌──────────────────┐
                            │ Coles Website     │
                            │ (HTML, WAF)       │
                            └──────────────────┘
```

Coles blocks server IPs with Incapsula WAF, so a proxy relay runs on a residential connection (Lappy) to fetch Coles search pages.

## Quick Start

### Local dev
```bash
pip install -r requirements.txt
python app.py  # runs on port 5000
```

### Docker
```bash
docker-compose up -d  # runs on port 5010
```

### Coles Proxy (required for Coles scraping)
```bash
# Run on Lappy with Python 3.11 (has requests installed)
'C:/Program Files/Python311/python.exe' coles_proxy.py
# Listens on port 8099
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/search?q=milk` | Search both stores, return matched products |
| `GET /api/product/<id>` | Single product with price history |
| `GET /api/compare/<id>` | Side-by-side store comparison |
| `GET /api/deals` | Products currently on special |
| `GET /api/categories` | List product categories |
| `GET /api/cheapest?store=coles` | Products cheaper at specified store |
| `GET /api/history/<id>?days=30` | Price history for a product |
| `GET /api/health` | Health check |

## Project Structure

```
app.py              # Flask web app — routes, search, comparison
config.py           # URLs, rate limits, user agents, scheduler config
models.py           # SQLite — products, prices, search cache
scheduler.py        # APScheduler — daily/weekly price refresh
coles_proxy.py      # Coles WAF bypass proxy (runs on Lappy)
scrapers/
  coles.py          # Coles HTML parser
  woolworths.py     # Woolworths JSON API client
  __init__.py       # Product matching (barcode + fuzzy name)
templates/          # Jinja2 HTML templates
static/             # CSS, JS, images
data/               # SQLite DB (gitignored)
```

## Price Matching

Products are matched across stores using two strategies:
1. **Barcode** (exact match) — primary, high confidence
2. **Name similarity** (threshold 0.65) — fallback for unmatched products

Results are sorted by savings percentage so the best deals appear first.

## Scheduler

- **Daily at 2 AM** — refreshes prices for 60+ grocery staples
- **Monday** — full category scrape, up to 60 results per query

## Requirements

- Python 3.11+ (3.11 for Coles proxy which needs `requests`)
- Flask, requests, APScheduler
- Docker (for production deployment)

## License

MIT
