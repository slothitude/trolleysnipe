"""Coles proxy relay — runs on Lappy to bypass Incapsula WAF.
Uses Flask + requests (which handles TLS/headers correctly).
Listens on port 8099. Must run on Python 3.11 which has requests installed."""

import sys
import random

try:
    from flask import Flask, request as req, Response
    import requests as http_requests
except ImportError:
    print("ERROR: flask and requests required. Run with Python 3.11:")
    print("  'C:/Program Files/Python311/python.exe coles_proxy.py'")
    sys.exit(1)

app = Flask(__name__)

COLES_URL = "https://www.coles.com.au/search/products"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


@app.route("/")
def proxy():
    query = req.args.get("q", "")
    page = req.args.get("page", "1")

    if not query:
        return "Missing q parameter", 400

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Referer": "https://www.coles.com.au/",
    }

    try:
        r = http_requests.get(
            COLES_URL,
            params={"q": query, "page": page},
            headers=headers,
            timeout=20,
        )
        return Response(r.content, mimetype="text/html; charset=utf-8")
    except Exception as e:
        return f"Proxy error: {e}", 502


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    print(f"Coles proxy relay running on port 8099 (Python {sys.version})")
    app.run(host="0.0.0.0", port=8099, threaded=True)
