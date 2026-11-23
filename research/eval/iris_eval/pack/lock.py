"""Lock files: ``eval/locks/<dataset>.lock.json`` (schema ``iris-lock/1``).

The first run of ``fetch_pack`` records the size and sha256 of every file it writes under
``raw/<dataset>/``, and the identity (size, ETag, figshare version) of every remote source it
read. Later runs verify against the lock: a local file that no longer matches is fetched again
and must then match; a remote archive whose size changed is refused. Once a run has completed,
files that are not in the lock are refused unless ``--update-lock`` is given.

Locks hold sizes, hashes, URLs and file names (page IDs) only, never content, so they are
committed like the frozen split lists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

LOCK_SCHEMA = "iris-lock/1"


class LockError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Lock:
    def __init__(self, path: Path, dataset: str, update: bool = False) -> None:
        self.path = path
        self.dataset = dataset
        self.update = update
        self.existed = path.is_file()
        if self.existed:
            with path.open(encoding="utf-8") as f:
                d = json.load(f)
            if d.get("schema") != LOCK_SCHEMA or d.get("dataset") != dataset:
                raise LockError(f"{path} is not an {LOCK_SCHEMA} lock for {dataset}")
            self.data: dict[str, Any] = d
        else:
            self.data = {"schema": LOCK_SCHEMA, "dataset": dataset, "complete": False, "sources": {}, "files": {}}
        self.added: list[str] = []

    @property
    def open_for_new(self) -> bool:
        return not self.data.get("complete") or self.update

    # files
    def entry(self, rel: str) -> dict[str, Any] | None:
        e: dict[str, Any] | None = self.data["files"].get(rel)
        return e

    def matches(self, rel: str, path: Path) -> bool:
        e = self.entry(rel)
        return bool(e and path.is_file() and path.stat().st_size == e["bytes"] and sha256_file(path) == e["sha256"])

    def record(self, rel: str, size: int, sha256: str) -> None:
        e = self.entry(rel)
        if e is not None:
            if e["bytes"] != size or e["sha256"] != sha256:
                raise LockError(
                    f"{self.dataset}/{rel}: fetched file does not match the lock "
                    f"({size} bytes, sha256 {sha256[:12]}... vs {e['bytes']} bytes, {e['sha256'][:12]}...)"
                )
            return
        if not self.open_for_new:
            raise LockError(f"{self.dataset}/{rel} is not in {self.path.name}; rerun with --update-lock to add it")
        self.data["files"][rel] = {"bytes": size, "sha256": sha256}
        self.added.append(rel)

    # sources
    def check_source(self, name: str, info: dict[str, Any]) -> None:
        """Record a remote source's identity, or refuse when it differs from the lock."""
        known = self.data["sources"].get(name)
        if known is None:
            if not self.open_for_new:
                raise LockError(f"{self.dataset}: source {name!r} is not in the lock; rerun with --update-lock")
            self.data["sources"][name] = info
            return
        for k in ("bytes", "url", "figshare_file_id", "sha256"):
            if known.get(k) is not None and info.get(k) is not None and known[k] != info[k]:
                raise LockError(
                    f"{self.dataset}: source {name!r} changed since the lock was written "
                    f"({k}: {known[k]} -> {info[k]}). Do not update without an orchestrator decision."
                )
        for k, v in info.items():
            known.setdefault(k, v)

    def save(self, complete: bool) -> None:
        if complete:
            self.data["complete"] = True
        self.data["files"] = dict(sorted(self.data["files"].items()))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(self.data, f, indent=1)
            f.write("\n")
        tmp.replace(self.path)
