"""A tiny zero-dependency web server built on the standard library.

Serves the static dashboard from ``web/`` and a small JSON API under ``/api``.
"""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import Subscription, summarize
from .importer import detect_recurring
from .store import Store

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        # Silence the default noisy logging; keep it to one tidy line.
        def log_message(self, fmt, *args):
            print(f"  {self.command} {self.path} -> {args[1]}")

        # ---- helpers -------------------------------------------------
        def _send_json(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(length).decode() if length else ""

        def _send_static(self, rel: str):
            if rel in ("", "/"):
                rel = "index.html"
            target = (WEB_DIR / rel.lstrip("/")).resolve()
            if not str(target).startswith(str(WEB_DIR)) or not target.is_file():
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # ---- routing -------------------------------------------------
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/subscriptions":
                self._send_json([s.to_dict() for s in store.all()])
            elif path == "/api/summary":
                self._send_json(summarize(store.all()))
            else:
                self._send_static(path)

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/subscriptions":
                self._handle_add()
            elif path == "/api/import":
                self._handle_import()
            else:
                self.send_error(404)

        def do_DELETE(self):
            path = urlparse(self.path).path
            if path == "/api/subscriptions":
                qs = parse_qs(urlparse(self.path).query)
                sub_id = qs.get("id", [None])[0]
                if sub_id and store.delete(int(sub_id)):
                    self._send_json({"deleted": int(sub_id)})
                else:
                    self.send_error(404)
            else:
                self.send_error(404)

        # ---- handlers ------------------------------------------------
        def _handle_add(self):
            try:
                data = json.loads(self._read_body())
                sub = Subscription(
                    name=data["name"],
                    amount=float(data["amount"]),
                    currency=data.get("currency", "USD"),
                    cycle=data.get("cycle", "monthly"),
                    next_charge=data.get("next_charge") or None,
                    category=data.get("category", "other"),
                )
                saved = store.add(sub)
                self._send_json(saved.to_dict(), status=201)
            except (KeyError, ValueError, TypeError) as exc:
                self._send_json({"error": str(exc)}, status=400)

        def _handle_import(self):
            try:
                data = json.loads(self._read_body())
                csv_text = data.get("csv", "")
                currency = data.get("currency", "USD")
                candidates = detect_recurring(csv_text, currency=currency)
                self._send_json([c.to_dict() for c in candidates])
            except (ValueError, TypeError) as exc:
                self._send_json({"error": str(exc)}, status=400)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, db: str | None = None) -> None:
    store = Store(db) if db else Store()
    handler = make_handler(store)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"SubTracker running at http://{host}:{port}  (Ctrl+C to stop)")
    print(f"Database: {store.path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        httpd.server_close()
        store.close()
