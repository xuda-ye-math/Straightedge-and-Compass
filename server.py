"""Minimal stdlib HTTP server for the n-gon animator (no third-party deps).

Serves the static frontend in ``web/`` and one JSON API endpoint:

    GET /api/construct?n=<int>   ->   construction document (from cache, else built live)

Run:
    .venv/bin/python server.py --port 8000
then open http://localhost:8000/ in a browser.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend import cache
from backend.constructible import FERMAT_PRIME_SET
from backend.construct import build

WEB_DIR = Path(__file__).resolve().parent / "web"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

# Building these on demand is slow (huge streams); require a pre-generated cache file.
_HEAVY = {65537}


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, "not found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        parsed = urlparse(self.path)
        if parsed.path == "/api/construct":
            self._handle_construct(parse_qs(parsed.query))
            return
        # static files
        rel = parsed.path.lstrip("/") or "index.html"
        self._send_file((WEB_DIR / rel).resolve())

    def _handle_construct(self, query: dict) -> None:
        raw = (query.get("n") or [""])[0]
        try:
            n = int(raw)
        except ValueError:
            self._send_json({"error": "请输入一个正整数 n"}, status=400)
            return
        if n < 1:
            self._send_json({"error": "n 必须是正整数"}, status=400)
            return
        # Cache hit: stream the file's raw bytes (avoid parsing + re-serializing, which
        # matters for the 65 MB 65537-gon).
        path = cache.path_for(n)
        if path.exists():
            self._send_file(path)
            return
        if n in _HEAVY:
            self._send_json({
                "n": n, "constructible": True, "supported": False,
                "note": f"正 {n} 边形可作图，但命令流过大，请先用 CLI 预生成缓存。",
                "commands": [],
            })
            return
        doc = build(n)
        # Only the Fermat-prime building blocks are persisted on the server; every other
        # n is built on demand and cached client-side (browser IndexedDB).
        if doc.get("constructible") and n in FERMAT_PRIME_SET:
            cache.save(doc)
        self._send_json(doc)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[server] {self.address_string()} {fmt % args}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the n-gon construction animator.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[server] serving {WEB_DIR} on http://{args.host}:{args.port}/  (Ctrl-C to stop)",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
