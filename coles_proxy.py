"""Coles proxy relay — runs on Lappy to bypass Incapsula WAF.
Listens on port 8099, fetches Coles search pages with residential headers,
returns the HTML so TrolleySnipe on Oracle can parse it."""

import json
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

COLES_URL = "https://www.coles.com.au/search/products"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


class ColesProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        query = params.get("q", [""])[0]
        page = params.get("page", ["1"])[0]

        if not query:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing q parameter")
            return

        url = f"{COLES_URL}?q={query}&page={page}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-AU,en;q=0.9",
            "Accept-Encoding": "identity",
            "Referer": "https://www.coles.com.au/",
        }

        try:
            req = Request(url, headers=headers)
            resp = urlopen(req, timeout=20)
            html = resp.read()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def log_message(self, *args):
        pass  # Suppress logs


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8099), ColesProxyHandler)
    print("Coles proxy relay running on port 8099")
    server.serve_forever()
