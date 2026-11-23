"""Opening a manifest's ``pack.sources`` and writing the files a page needs.

Source kinds (``kind`` in the manifest):

- ``file``: one file downloaded whole (``url``, ``dest``; optional pinned ``sha256``/``md5``/``bytes``).
- ``zip``: an archive. ``access: "range"`` (default) reads the central directory and the chosen
  members with HTTP range requests; ``access: "whole"`` downloads the archive once (small archives,
  or hosts without range support) and reads members locally. A range source may fall back to a
  whole download when the server ignores ``Range``, but only up to ``whole_max_bytes`` (and the
  run's ``--max-whole-gb``); otherwise the run stops and says why. An archive whose publisher
  protects it with a password (``password_required``) is opened with a password the person
  running the fetch supplies at run time (``--archive-password`` or the source's ``password_env``
  variable); passwords are never stored in the repository (ZipCrypto only).
- ``url-files``: individual files under ``base_url`` (one request per page file).
- ``figshare-zip``: a ``zip`` whose URL is resolved from the figshare API (``article``, a
  ``file_regex`` that must match exactly one file); the resolved file id, size and md5 are
  recorded in the lock.

Members are written to ``raw/<dataset>/<source name>/<member path>`` (see ``safepath``).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import urllib.parse
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lock import Lock, sha256_file
from .remote import FetchError, RangeNotSupported, RemoteFile, download, get_json
from .safepath import as_path, safe_relpath, storage_rel

FIGSHARE_API = "https://api.figshare.com/v2"
KINDS = ("file", "zip", "url-files", "figshare-zip")


@dataclass(frozen=True)
class FileRef:
    """One file a page needs: ``member`` of ``source`` (None for a whole-file source)."""

    source: str
    member: str | None
    rel: str
    role: str


class Context:
    """What a planner may use: archive directories, small index files, and the fetch itself."""

    def __init__(self, manifest: dict[str, Any], raw: Path, lock: Lock, max_whole_bytes: int,
                 log: Callable[[str], None] = print, passwords: dict[str, str] | None = None) -> None:
        self.manifest = manifest
        self.dataset = manifest["id"]
        self.pack: dict[str, Any] = manifest["pack"]
        self.raw = raw
        self.lock = lock
        self.max_whole_bytes = max_whole_bytes
        self.log = log
        self.passwords = passwords or {}  # source name -> archive password, given at run time
        self._sources = {s["name"]: s for s in self.pack["sources"]}
        self._zips: dict[str, zipfile.ZipFile] = {}
        self._remotes: dict[str, RemoteFile] = {}
        self.whole_bytes = 0
        self.member_bytes = 0
        self.fetched_files = 0
        self.reused_files = 0

    # bookkeeping
    @property
    def bytes_downloaded(self) -> int:
        return self.whole_bytes + sum(r.bytes_fetched for r in self._remotes.values())

    def source(self, name: str) -> dict[str, Any]:
        if name not in self._sources:
            raise FetchError(f"{self.dataset}: manifest has no source {name!r}")
        src: dict[str, Any] = self._sources[name]
        return src

    def close(self) -> None:
        for z in self._zips.values():
            z.close()
        self._zips.clear()

    # whole files
    def _whole(self, name: str, url: str, dest_rel: str, pins: dict[str, Any]) -> Path:
        path = as_path(self.raw, dest_rel)
        if self.lock.matches(dest_rel, path):
            self.reused_files += 1
            return path
        if path.is_file() and self.lock.entry(dest_rel) is None and _pins_ok(path, pins):
            self.lock.record(dest_rel, path.stat().st_size, sha256_file(path))
            self.reused_files += 1
            return path
        self.log(f"{self.dataset}: downloading {dest_rel} from {urllib.parse.urlparse(url).netloc}")
        got = download(url, path, progress=self.log)
        self.whole_bytes += got["bytes"]
        self.fetched_files += 1
        problems = _pin_problems(got, pins)
        if problems:
            bad = path.with_name(path.name + ".rejected")
            path.replace(bad)
            raise FetchError(f"{self.dataset}/{dest_rel}: checksum failed: {'; '.join(problems)} (kept as {bad.name})")
        self.lock.record(dest_rel, got["bytes"], got["sha256"])
        return path

    def file_path(self, name: str) -> Path:
        s = self.source(name)
        if s["kind"] != "file":
            raise FetchError(f"{self.dataset}: source {name!r} is not a whole file")
        return self._whole(name, s["url"], s["dest"], s)

    # archives
    def zip(self, name: str) -> zipfile.ZipFile:
        if name in self._zips:
            return self._zips[name]
        s = self.source(name)
        if s["kind"] not in ("zip", "figshare-zip"):
            raise FetchError(f"{self.dataset}: source {name!r} is not an archive")
        url = s.get("url")
        if s["kind"] == "figshare-zip":
            url = self._resolve_figshare(name, s)
        assert url
        dest = s.get("dest") or f"{name}.zip"
        if s.get("access", "range") == "whole":
            z = zipfile.ZipFile(self._whole(name, url, dest, s))
        else:
            try:
                rf = RemoteFile(url)
            except RangeNotSupported as exc:
                cap = min(int(s.get("whole_max_bytes") or 0), self.max_whole_bytes)
                if exc.total is not None and exc.total <= cap:
                    self.log(f"{self.dataset}: {name}: server ignores range requests; downloading the whole "
                             f"archive ({exc.total / 1e6:.0f} MB) instead")
                    z = zipfile.ZipFile(self._whole(name, url, dest, s))
                    self._zips[name] = z
                    return z
                size = f"{exc.total / 1e9:.1f} GB" if exc.total else "unknown size"
                raise FetchError(
                    f"{self.dataset}: {name}: the server does not support range requests and the whole archive "
                    f"({size}) is over the limit for a whole download "
                    f"({cap / 1e9:.1f} GB); not downloading. Report this to the orchestrator."
                ) from exc
            if s.get("bytes") is not None and rf.size != int(s["bytes"]):
                raise FetchError(f"{self.dataset}: {name}: remote archive is {rf.size} bytes, "
                                 f"manifest pins {s['bytes']}")
            self.lock.check_source(name, {"url": url, "bytes": rf.size, "etag": rf.etag,
                                          "last_modified": rf.last_modified, "access": "range"})
            # The end-of-archive records (including zip64) sit in the last 64 KiB.
            rf.prefetch(rf.size - (1 << 16) - 22, (1 << 16) + 22)
            self._remotes[name] = rf
            z = zipfile.ZipFile(rf)
        self._zips[name] = z
        return z

    def _resolve_figshare(self, name: str, s: dict[str, Any]) -> str:
        api = s.get("api") or FIGSHARE_API
        item = get_json(f"{api}/articles/{s['article']}")
        files = item.get("files") or []
        pat = re.compile(s["file_regex"])
        hits = [f for f in files if pat.search(str(f.get("name", "")))]
        if len(hits) != 1:
            listing = "; ".join(f"{f.get('name')} ({int(f.get('size') or 0) / 1e9:.2f} GB)" for f in files)
            raise FetchError(
                f"{self.dataset}: {name}: figshare item {s['article']} has {len(hits)} files matching "
                f"{s['file_regex']!r} (need exactly 1). Files: {listing}. Report this to the orchestrator."
            )
        f = hits[0]
        self.lock.check_source(name, {"figshare_article": s["article"], "figshare_version": item.get("version"),
                                      "figshare_file_id": f.get("id"), "file_name": f.get("name"),
                                      "bytes": f.get("size"), "md5": f.get("computed_md5") or f.get("supplied_md5")})
        url: str = f["download_url"]
        return url

    def infolist(self, name: str) -> list[zipfile.ZipInfo]:
        return [i for i in self.zip(name).infolist() if not i.is_dir()]

    def names(self, name: str) -> list[str]:
        return [i.filename for i in self.infolist(name)]

    def _extract(self, name: str, member: str, path: Path) -> None:
        s = self.source(name)
        z = self.zip(name)
        info = z.getinfo(member)
        rf = self._remotes.get(name)
        if rf is not None:
            rf.prefetch(info.header_offset, 30 + len(info.filename.encode("utf-8")) + len(info.extra) + 1024
                        + info.compress_size)
        pw = self.passwords.get(name)
        pwd = pw.encode("utf-8") if pw else None
        if s.get("password_required") and pwd is None:
            raise FetchError(f"{self.dataset}: {name}: archive password not given")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        try:
            with z.open(info, pwd=pwd) as src, tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        except NotImplementedError as exc:
            tmp.unlink(missing_ok=True)
            raise FetchError(f"{self.dataset}: {member}: archive uses a method the standard library cannot read "
                             f"({exc}); report this to the orchestrator") from exc
        except (RuntimeError, zipfile.BadZipFile) as exc:
            tmp.unlink(missing_ok=True)
            raise FetchError(f"{self.dataset}: {member}: could not read member ({exc})") from exc
        tmp.replace(path)
        self.member_bytes += info.compress_size

    # the files a page needs
    def materialise(self, ref: FileRef) -> Path:
        path = as_path(self.raw, ref.rel)
        if self.lock.matches(ref.rel, path):
            self.reused_files += 1
            return path
        s = self.source(ref.source)
        if ref.member is None:
            if s["kind"] != "file":
                raise FetchError(f"{self.dataset}: {ref.rel}: source {ref.source!r} needs a member name")
            return self._whole(ref.source, s["url"], s["dest"], s)
        if s["kind"] == "url-files":
            url = s["base_url"].rstrip("/") + "/" + urllib.parse.quote(safe_relpath(ref.member))
            got = download(url, path)
            self.whole_bytes += got["bytes"]
        else:
            self._extract(ref.source, ref.member, path)
        self.fetched_files += 1
        self.lock.record(ref.rel, path.stat().st_size, sha256_file(path))
        return path

    def member_ref(self, source: str, member: str, role: str) -> FileRef:
        return FileRef(source, member, storage_rel(source, member), role)

    def read_member(self, source: str, member: str) -> Path:
        """Fetch an index file kept with the data (e.g. COCO test.json) and return its local path."""
        return self.materialise(self.member_ref(source, member, "index"))


def _pin_problems(got: dict[str, Any], pins: dict[str, Any]) -> list[str]:
    problems = []
    if pins.get("bytes") is not None and got["bytes"] != int(pins["bytes"]):
        problems.append(f"size {got['bytes']} != pinned {pins['bytes']}")
    for algo in ("sha256", "md5"):
        if pins.get(algo) and got[algo] != pins[algo]:
            problems.append(f"{algo} {got[algo]} != pinned {pins[algo]}")
    return problems


def _pins_ok(path: Path, pins: dict[str, Any]) -> bool:
    """True when an existing file matches the manifest's pins (and there is at least one pin)."""
    if not (pins.get("sha256") or pins.get("md5")):
        return False
    got: dict[str, Any] = {"bytes": path.stat().st_size, "sha256": sha256_file(path), "md5": ""}
    if pins.get("md5"):
        h = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        got["md5"] = h.hexdigest()
    return not _pin_problems(got, pins)
