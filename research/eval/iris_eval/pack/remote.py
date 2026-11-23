"""HTTP access for data packs: whole downloads with retries, and range reads.

``RemoteFile`` is a read-only, seekable file over HTTP range requests. ``zipfile.ZipFile`` can
open it like a local file: it reads the archive's central directory (the list of members) from
the end of the file, then each member's bytes from its offset, so one page of a 28 GB archive
costs the directory plus that page. Each member's CRC-32 is checked by ``zipfile`` as it is read.

A server that ignores ``Range`` (answers ``200`` with the whole file) raises
``RangeNotSupported``; the caller then decides whether downloading the whole file is acceptable.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from http.client import HTTPResponse
from pathlib import Path
from typing import Any

USER_AGENT = "iris-eval-fetch/1 (python-urllib)"
CHUNK = 1 << 20
RETRIES = 4
RETRY_DELAY = 2.0  # seconds, multiplied by the attempt number; tests set it to 0
TIMEOUT = 60
_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+|\*)")


class FetchError(RuntimeError):
    pass


class RangeNotSupported(FetchError):
    def __init__(self, url: str, total: int | None) -> None:
        super().__init__(f"server does not support range requests: {url}")
        self.total = total


def host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


def _open(url: str, headers: dict[str, str] | None = None) -> HTTPResponse:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp: HTTPResponse = urllib.request.urlopen(req, timeout=TIMEOUT)
            return resp
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504):
                raise FetchError(f"HTTP {exc.code} from {host_of(url)} for {url}") from exc
            last = exc
        except (urllib.error.URLError, OSError) as exc:
            last = exc
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY * attempt)
    raise FetchError(f"host {host_of(url)} not reachable ({last})") from last


def get_json(url: str) -> Any:
    with _open(url, {"Accept": "application/json"}) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url: str, dest: Path, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Download ``url`` to ``dest`` (via ``dest.part``); return its size, sha256 and md5."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    sha, md5 = hashlib.sha256(), hashlib.md5()
    done = 0
    try:
        with _open(url) as r, tmp.open("wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            next_report = 0.25
            for chunk in iter(lambda: r.read(CHUNK), b""):
                f.write(chunk)
                sha.update(chunk)
                md5.update(chunk)
                done += len(chunk)
                if progress and total > 50 * CHUNK and done / total >= next_report:
                    progress(f"  {dest.name}: {100 * done // total}% of {total / 1e6:.0f} MB")
                    next_report += 0.25
            if total and done != total:
                raise FetchError(f"truncated download of {url}: {done} of {total} bytes")
    except (OSError, FetchError) as exc:
        tmp.unlink(missing_ok=True)
        if isinstance(exc, FetchError):
            raise
        raise FetchError(f"download of {url} failed ({exc})") from exc
    tmp.replace(dest)
    return {"bytes": done, "sha256": sha.hexdigest(), "md5": md5.hexdigest()}


class RemoteFile(io.RawIOBase):
    """A read-only, seekable view of a remote file through HTTP range requests."""

    def __init__(self, url: str, block: int = 1 << 16) -> None:
        super().__init__()
        self.url = url
        self.block = block
        self.pos = 0
        self.bytes_fetched = 0
        self.requests = 0
        self._cache_start = 0
        self._cache = b""
        with _open(url, {"Range": "bytes=0-0"}) as r:
            if r.status != 206:
                length = r.headers.get("Content-Length")
                raise RangeNotSupported(url, int(length) if length else None)
            m = _CONTENT_RANGE.match(r.headers.get("Content-Range", ""))
            if not m or m.group(3) == "*":
                raise RangeNotSupported(url, None)
            self.size = int(m.group(3))
            self.etag = r.headers.get("ETag")
            self.last_modified = r.headers.get("Last-Modified")
            r.read()
        self.requests += 1

    # io plumbing
    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            new = offset
        elif whence == io.SEEK_CUR:
            new = self.pos + offset
        elif whence == io.SEEK_END:
            new = self.size + offset
        else:
            raise ValueError(f"bad whence {whence}")
        if new < 0:
            raise ValueError("negative seek position")
        self.pos = new
        return new

    def _fetch(self, start: int, end: int) -> bytes:
        """Bytes [start, end) of the remote file, in one request (retried on short reads)."""
        last: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                with _open(self.url, {"Range": f"bytes={start}-{end - 1}"}) as r:
                    m = _CONTENT_RANGE.match(r.headers.get("Content-Range", ""))
                    if r.status != 206 or not m or int(m.group(1)) != start:
                        raise RangeNotSupported(self.url, None)
                    data = r.read()
                if len(data) == end - start:
                    self.bytes_fetched += len(data)
                    self.requests += 1
                    return data
                last = FetchError(f"short range read from {self.url}: {len(data)} of {end - start} bytes")
            except OSError as exc:
                last = exc
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY * attempt)
        raise FetchError(str(last)) from last

    def prefetch(self, start: int, length: int) -> None:
        """Load bytes [start, start + length) with a single request (e.g. one whole member)."""
        start = max(0, start)
        end = min(self.size, start + length)
        if self._cache_start <= start and end <= self._cache_start + len(self._cache):
            return
        if end > start:
            self._cache = self._fetch(start, end)
            self._cache_start = start

    def read(self, size: int | None = -1) -> bytes:
        if self.pos >= self.size:
            return b""
        n = self.size - self.pos if size is None or size < 0 else min(size, self.size - self.pos)
        out = bytearray()
        while len(out) < n:
            p = self.pos
            off = p - self._cache_start
            if not (0 <= off < len(self._cache)):
                end = min(self.size, p + max(n - len(out), self.block))
                self._cache = self._fetch(p, end)
                self._cache_start = p
                off = 0
            take = self._cache[off : off + n - len(out)]
            out += take
            self.pos += len(take)
        return bytes(out)

    def readinto(self, b: Any) -> int:
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)
