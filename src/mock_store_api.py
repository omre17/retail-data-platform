"""Small independent HTTP source for practicing REST ingestion locally."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ROUTES = {
    "/products": ROOT / "data/raw/products.json",
    "/orders": ROOT / "data/raw/api_orders.json",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            body = b'{"status":"ok"}'
        elif path in ROUTES:
            try:
                body = ROUTES[path].read_bytes()
            except OSError:
                self.send_error(500, "Source data unavailable")
                return
        else:
            self.send_error(404, "Unknown endpoint")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
