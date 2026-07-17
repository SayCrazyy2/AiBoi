"""
A tiny health-check HTTP server -- nothing more. Railway (and similar
PaaS platforms) can be configured to health-check a service over HTTP, and
some service types expect *something* bound to $PORT even for a
background worker. This exists purely to satisfy that, running in a
background thread alongside the actual bots.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional


class _Handler(BaseHTTPRequestHandler):
    status_fn: Optional[Callable[[], str]] = None

    def do_GET(self) -> None:  # noqa: N802 -- stdlib naming convention
        if self.path in ("/", "/health", "/healthz"):
            body = (self.status_fn() if self.status_fn else "ok").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        pass  # keep bot logs free of health-check noise


def start_health_server(port: int, status_fn: Optional[Callable[[], str]] = None) -> ThreadingHTTPServer:
    _Handler.status_fn = status_fn
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[health] listening on :{port} (/, /health, /healthz)")
    return server
