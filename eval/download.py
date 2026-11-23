#!/usr/bin/env python3
"""Download, checksum and unpack evaluation datasets listed in eval/manifests/.

    python eval/download.py --list
    python eval/download.py pubtabnet-final-eval
    python eval/download.py --all

Data goes to ``eval/.data/raw/<dataset>/`` (git-ignored; override the root with
``IRIS_EVAL_DATA`` or ``--data-dir``). Each file is checked against the ``sha256`` (or ``md5``)
and ``bytes`` pinned in its manifest; archives are unpacked to ``raw/<dataset>/unpacked/<file>/``
with path-traversal protection.

Licence gate (docs/DECISIONS.md O4): ``excluded`` datasets are refused;
``evaluation-only`` ones need ``--accept-eval-only`` (owner decision, O4 amendment).
For a sample-only download of just the pages the splits need, use ``eval/fetch_pack.py``.
Files with no pinned checksum need ``--allow-unpinned``, which prints the sha256 to pin.

Standard library only, so it runs before anything is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MANIFEST_DIR = HERE / "manifests"
CHUNK = 1 << 20


class DownloadError(RuntimeError):
    pass


def data_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("IRIS_EVAL_DATA")
    return Path(env).resolve() if env else HERE / ".data"


def load_manifests(manifest_dir: Path = MANIFEST_DIR) -> dict[str, dict[str, Any]]:
    out = {}
    for p in sorted(manifest_dir.glob("*.json")):
        with p.open(encoding="utf-8") as f:
            m = json.load(f)
        out[m["id"]] = m
    return out


def file_digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, spec: dict[str, Any]) -> list[str]:
    """Return a list of problems (empty when the file matches its pinned size and checksum)."""
    problems = []
    if spec.get("bytes") is not None and path.stat().st_size != int(spec["bytes"]):
        problems.append(f"size {path.stat().st_size} != pinned {spec['bytes']}")
    for algo in ("sha256", "md5"):
        if spec.get(algo):
            got = file_digest(path, algo)
            if got != spec[algo]:
                problems.append(f"{algo} {got} != pinned {spec[algo]}")
    return problems


def fetch(url: str, dest: Path) -> None:
    host = urllib.parse.urlparse(url).netloc
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "iris-eval-download/1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            next_report = 0.1
            for chunk in iter(lambda: r.read(CHUNK), b""):
                f.write(chunk)
                done += len(chunk)
                if total and done / total >= next_report:
                    print(f"  {dest.name}: {100 * done // total}%", flush=True)
                    next_report += 0.1
    except (urllib.error.URLError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"not downloaded: host {host} not reachable ({exc})") from exc
    tmp.replace(dest)


def _safe_target(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise DownloadError(f"archive member escapes target folder: {name!r}")
    return target


def unpack(archive: Path, kind: str, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    root = out.resolve()
    if kind == "zip":
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                _safe_target(root, info.filename)
            z.extractall(root)
    elif kind in ("tar", "tar.gz", "tgz"):
        with tarfile.open(archive) as t:
            for member in t.getmembers():
                _safe_target(root, member.name)
                if member.issym() or member.islnk() or member.isdev():
                    raise DownloadError(f"archive has a link or device member: {member.name!r}")
            t.extractall(root)
    else:
        raise DownloadError(f"unknown archive kind {kind!r}")


def download(m: dict[str, Any], root: Path, accept_eval_only: bool, allow_unpinned: bool) -> None:
    ds = m["id"]
    if m["use"] == "excluded":
        raise DownloadError(f"{ds} is excluded ({m.get('use_reason', 'licence')}); not downloading")
    if m["use"] in ("evaluation-only", "evaluation-only-needs-decision") and not accept_eval_only:
        raise DownloadError(f"{ds}: evaluation-only licence; needs an owner decision and --accept-eval-only")
    if not m["files"]:
        raise DownloadError(f"{ds}: manifest lists no files yet")
    raw = root / "raw" / ds
    for spec in m["files"]:
        dest = raw / spec["dest"]
        pinned = bool(spec.get("sha256") or spec.get("md5"))
        if not pinned and not allow_unpinned:
            raise DownloadError(f"{ds}/{spec['dest']}: no pinned checksum; use --allow-unpinned to fetch and pin")
        if dest.is_file() and pinned and not verify(dest, spec):
            print(f"{ds}/{spec['dest']}: already present and verified")
        else:
            print(f"{ds}/{spec['dest']}: downloading {spec['url']}")
            raw.mkdir(parents=True, exist_ok=True)
            fetch(spec["url"], dest)
            problems = verify(dest, spec)
            if problems:
                bad = dest.with_name(dest.name + ".rejected")
                dest.replace(bad)
                raise DownloadError(f"{ds}/{spec['dest']}: checksum failed: {'; '.join(problems)} (kept as {bad.name})")
            if not pinned:
                print(f"{ds}/{spec['dest']}: UNPINNED, sha256={file_digest(dest, 'sha256')} "
                      f"bytes={dest.stat().st_size}; pin these in the manifest")
            else:
                print(f"{ds}/{spec['dest']}: verified")
        if spec.get("unpack"):
            unpack(dest, spec["unpack"], raw / "unpacked" / spec["dest"])
            print(f"{ds}/{spec['dest']}: unpacked")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datasets", nargs="*")
    ap.add_argument("--all", action="store_true", help="every dataset whose use is 'allowed'")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--data-dir")
    ap.add_argument("--accept-eval-only", action="store_true")
    ap.add_argument("--allow-unpinned", action="store_true")
    a = ap.parse_args(argv)
    manifests = load_manifests()
    if a.list:
        for m in manifests.values():
            print(f"{m['id']:28} {m['use']:32} {', '.join(m['categories'])}")
        return 0
    ids = [i for i, m in manifests.items() if m["use"] == "allowed"] if a.all else a.datasets
    if not ids:
        ap.print_usage()
        return 1
    root = data_root(a.data_dir)
    failed = 0
    for ds in ids:
        if ds not in manifests:
            print(f"{ds}: no manifest", file=sys.stderr)
            failed += 1
            continue
        try:
            download(manifests[ds], root, a.accept_eval_only, a.allow_unpinned)
        except DownloadError as exc:
            print(str(exc), file=sys.stderr)
            failed += 1
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
