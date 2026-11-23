"""A local HTTP server for data-pack tests: serves in-memory files, honours Range unless told not to,
and counts the bytes it sends per path."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeServer:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.no_range: set[str] = set()
        self.sent: dict[str, int] = {}
        self.requests: list[tuple[str, str | None]] = []
        self.base = ""

    def add(self, path: str, data: bytes, *, ranges: bool = True) -> str:
        self.files[path] = data
        if not ranges:
            self.no_range.add(path)
        return self.base + path

    def url(self, path: str) -> str:
        return self.base + path


def _handler(srv: FakeServer) -> type[BaseHTTPRequestHandler]:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            rng = self.headers.get("Range")
            srv.requests.append((path, rng))
            data = srv.files.get(path)
            if data is None:
                self.send_response(404)
                self.end_headers()
                return
            m = re.match(r"bytes=(\d+)-(\d*)$", rng or "")
            if m and path not in srv.no_range:
                start = int(m.group(1))
                end = min(int(m.group(2)) if m.group(2) else len(data) - 1, len(data) - 1)
                body = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            else:
                body = data
                self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("ETag", f'"{len(data)}"')
            srv.sent[path] = srv.sent.get(path, 0) + len(body)
            self.end_headers()
            self.wfile.write(body)

    return H


@contextmanager
def serve() -> Iterator[FakeServer]:
    srv = FakeServer()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(srv))
    srv.base = f"http://127.0.0.1:{httpd.server_address[1]}"
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        httpd.shutdown()
        httpd.server_close()
