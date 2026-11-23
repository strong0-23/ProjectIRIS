"""One data-pack run per dataset: gate, list pages, split, check the frozen split, fetch, lock.

Writes, for dataset ``<ds>``:

- ``<data>/raw/<ds>/...``: only the files the split's pages need (plus small index files);
- ``<data>/raw/<ds>/pack.json`` (``iris-pack/1``): every page offered (ID, category, group,
  a few attributes) and, for the selected pages, the relative path of each file by role. The
  converters read their page list from it, so ``prepare`` recomputes exactly the same split;
- ``eval/locks/<ds>.lock.json``: sizes and sha256 of what was written (see ``lock``);
- ``eval/splits/<ds>.json``: the frozen split, written on the first run, checked on every run.

It prints counts and sizes only, never document content.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..splits import GROUPED_RULE, check_frozen, compute_splits, frozen_record
from .lock import Lock
from .planners import PLANNERS
from .remote import FetchError
from .sources import Context

PACK_SCHEMA = "iris-pack/1"


class PackRefused(RuntimeError):
    """The licence gate or the manifest does not allow a pack for this dataset."""


class PackSkipped(PackRefused):
    """Something only the person running the fetch can supply is missing (an archive password)."""


def archive_passwords(manifest: dict[str, Any], given: Mapping[str, str] | None) -> dict[str, str]:
    """Passwords for the sources that need one: ``given[<dataset>]`` or the source's ``password_env``.

    Raises ``PackSkipped`` with a pointer to the dataset page and licence when one is missing. The
    password is never read from or written to the repository.
    """
    ds = manifest["id"]
    out: dict[str, str] = {}
    for s in manifest["pack"]["sources"]:
        if not s.get("password_required"):
            continue
        env = s.get("password_env")
        pw = (given or {}).get(ds) or (os.environ.get(env) if env else None)
        if not pw:
            how = f"--archive-password {ds}=<password>" + (f" or set {env}" if env else "")
            raise PackSkipped(
                f"{ds}: skipped: the archive needs the password given on the dataset page "
                f"({manifest['homepage']}); read the licence ({manifest['licence']['url']}) there, then pass {how}"
            )
        out[s["name"]] = pw
    return out


@dataclass
class Result:
    dataset: str
    use: str
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    groups: dict[str, dict[str, int]] = field(default_factory=dict)
    downloaded_bytes: int = 0
    on_disk_bytes: int = 0
    fetched_files: int = 0
    reused_files: int = 0
    split_status: str = ""
    lock_status: str = ""


def gate(manifest: dict[str, Any], accept_eval_only: bool) -> None:
    ds, use = manifest["id"], manifest["use"]
    if use == "excluded":
        raise PackRefused(f"{ds} is excluded ({manifest.get('use_reason', 'licence')}); not downloading")
    if use == "evaluation-only-needs-decision":
        raise PackRefused(f"{ds}: evaluation-only licence without an owner decision; not downloading")
    if use == "evaluation-only" and not accept_eval_only:
        raise PackRefused(f"{ds}: approved for evaluation only (O4 amendment); add --accept-eval-only")
    if not manifest.get("pack"):
        raise PackRefused(f"{ds}: no data pack: {manifest.get('pack_reason', 'not defined')}")


def fetch_dataset(
    manifest: dict[str, Any],
    *,
    data_root: Path,
    lock_dir: Path,
    splits_dir: Path,
    accept_eval_only: bool = False,
    update_lock: bool = False,
    max_whole_bytes: int = 2 * 10**9,
    write_splits: bool = True,
    log: Callable[[str], None] = print,
    passwords: Mapping[str, str] | None = None,
) -> Result:
    gate(manifest, accept_eval_only)
    source_passwords = archive_passwords(manifest, passwords)
    ds = manifest["id"]
    pack = manifest["pack"]
    if pack["planner"] not in PLANNERS:
        raise PackRefused(f"{ds}: unknown planner {pack['planner']!r}")
    raw = data_root / "raw" / ds
    lock = Lock(lock_dir / f"{ds}.lock.json", ds, update=update_lock)
    ctx = Context(manifest, raw, lock, max_whole_bytes, log, source_passwords)
    res = Result(ds, manifest["use"])
    try:
        pages = PLANNERS[pack["planner"]](ctx)
        ids = [p.id for p in pages]
        if len(set(ids)) != len(ids):
            raise FetchError(f"{ds}: the planner listed duplicate page IDs")
        grouped = manifest["split"]["rule"] == GROUPED_RULE
        groups = {p.id: str(p.group) for p in pages} if grouped else None
        splits = compute_splits(manifest, [(p.id, p.category) for p in pages], groups)
        res.split_status = check_frozen(frozen_record(manifest, splits), splits_dir, write_splits)
        by_id = {p.id: p for p in pages}
        files: dict[str, dict[str, str]] = {}
        selected = sorted({i for s in splits.values() for i in s["dev"] + s["heldout"]})
        for n, pid in enumerate(selected, 1):
            for ref in by_id[pid].files:
                ctx.materialise(ref)
                files.setdefault(pid, {})[ref.role] = ref.rel
            if n % 25 == 0:
                log(f"{ds}: {n}/{len(selected)} pages ready")
        raw.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": PACK_SCHEMA,
            "dataset": ds,
            "split_rule": manifest["split"]["rule"],
            "population": [
                {"id": p.id, "category": p.category, **({"group": p.group} if grouped else {}),
                 **({"attrs": p.attrs} if p.attrs else {})}
                for p in pages
            ],
            "files": files,
        }
        with (raw / "pack.json").open("w", encoding="utf-8", newline="\n") as f:
            json.dump(record, f, indent=0)
        for cat, s in splits.items():
            avail = sum(1 for p in pages if p.category == cat)
            res.counts[cat] = {"available": avail, "dev": len(s["dev"]), "heldout": len(s["heldout"])}
            if grouped:
                res.groups[cat] = {"dev": s["dev_groups"], "heldout": s["heldout_groups"]}
        lock.save(complete=True)
        res.lock_status = ("lock written" if not lock.existed else
                           f"verified against lock (+{len(lock.added)} new)" if lock.added else "verified against lock")
    except BaseException:
        if lock.data["files"] or lock.data["sources"]:
            lock.save(complete=False)
        raise
    finally:
        res.downloaded_bytes = ctx.bytes_downloaded
        res.fetched_files = ctx.fetched_files
        res.reused_files = ctx.reused_files
        ctx.close()
    res.on_disk_bytes = sum(e["bytes"] for e in lock.data["files"].values())
    return res


def _mb(n: int) -> str:
    return f"{n / 1e6:,.1f} MB" if n < 1e9 else f"{n / 1e9:,.2f} GB"


def summary(results: list[Result], failures: dict[str, str], skipped: dict[str, str] | None = None) -> str:
    """The one-screen summary: pages per category and split, and sizes."""
    rows = [f"{'dataset':22} {'use':16} {'category':22} {'avail':>6} {'dev':>4} {'held':>4} "
            f"{'fetched now':>12} {'on disk':>11}"]
    total_now = total_disk = 0
    for r in results:
        first = True
        for cat, c in sorted(r.counts.items()):
            g = r.groups.get(cat)
            cat_s = cat + (f" ({g['dev']}/{g['heldout']} grp)" if g else "")
            rows.append(f"{r.dataset if first else '':22} {r.use if first else '':16} {cat_s:22} {c['available']:>6} "
                        f"{c['dev']:>4} {c['heldout']:>4} {(_mb(r.downloaded_bytes) if first else ''):>12} "
                        f"{(_mb(r.on_disk_bytes) if first else ''):>11}")
            first = False
        total_now += r.downloaded_bytes
        total_disk += r.on_disk_bytes
    for ds, why in sorted(failures.items()):
        rows.append(f"{ds:22} NOT FETCHED: {why}")
    for ds, why in sorted((skipped or {}).items()):
        rows.append(f"{ds:22} SKIPPED: {why}")
    rows.append(f"{'total':22} {'':16} {'':22} {'':>6} {'':>4} {'':>4} {_mb(total_now):>12} {_mb(total_disk):>11}")
    return "\n".join(rows)
