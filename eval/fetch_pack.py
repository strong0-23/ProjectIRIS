#!/usr/bin/env python3
"""Fetch the evaluation data pack: only the pages the split rule selects.

    python eval/fetch_pack.py --list
    python eval/fetch_pack.py --all --accept-eval-only
    python eval/fetch_pack.py cord-v2 doclaynet

For each dataset it lists the pages on offer (from archive directories or index files, never
from page content), applies the split rule, checks or writes the frozen split in
``eval/splits/``, downloads only the files of the dev and held-out pages (HTTP range requests
into remote archives where the host allows it), and records every file's size and sha256 in
``eval/locks/<dataset>.lock.json``; later runs verify against the lock.

Licence gate (docs/DECISIONS.md O4): ``excluded`` datasets are refused; datasets approved for
evaluation only need ``--accept-eval-only``. An archive its publisher protects with a password
(BLN600) needs that password at run time, read from the dataset page after its licence:
``--archive-password bln600=<password>`` or ``IRIS_BLN600_PASSWORD``; without it the dataset is
skipped. Passwords are never stored in the repository.

Data goes to ``eval/.data/`` (git-ignored) or ``--data-dir`` / ``IRIS_EVAL_DATA``. Held-out pages
are downloaded too, because they are scored on this machine; they are never exported
(eval/export_dev.py) and never opened by an agent.

Standard library only: runs on Windows, macOS and Linux before anything is installed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "research" / "eval"))

from iris_eval.manifests import ManifestError, list_manifests  # noqa: E402
from iris_eval.pack.fetch import PackRefused, PackSkipped, Result, fetch_dataset, summary  # noqa: E402
from iris_eval.pack.lock import LockError  # noqa: E402
from iris_eval.pack.remote import FetchError  # noqa: E402
from iris_eval.pack.safepath import UnsafePath  # noqa: E402
from iris_eval.splits import SplitMismatch  # noqa: E402

FETCHABLE = ("allowed", "evaluation-only")


def data_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("IRIS_EVAL_DATA")
    return Path(env).resolve() if env else HERE / ".data"


def _est(m: dict) -> str:  # type: ignore[type-arg]
    pack = m.get("pack") or {}
    b = (pack.get("estimate") or {}).get("bytes")
    return f"~{b / 1e6:,.0f} MB" if b else "-"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datasets", nargs="*")
    ap.add_argument("--all", action="store_true", help="every dataset with a pack that the licence gate allows")
    ap.add_argument("--list", action="store_true", help="list datasets, licence use and estimated download")
    ap.add_argument("--accept-eval-only", action="store_true",
                    help="include datasets approved for evaluation only (O4 amendment, 23 Nov 2026)")
    ap.add_argument("--data-dir")
    ap.add_argument("--lock-dir", default=str(HERE / "locks"))
    ap.add_argument("--splits-dir", default=str(HERE / "splits"))
    ap.add_argument("--update-lock", action="store_true", help="allow adding files that are not in the lock yet")
    ap.add_argument("--archive-password", action="append", default=[], metavar="DATASET=PASSWORD",
                    help="password for a dataset whose publisher protects its archive (repeatable)")
    ap.add_argument("--max-whole-gb", type=float, default=2.0,
                    help="largest archive downloaded whole when a host ignores range requests (default 2)")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows consoles: never crash on a file name
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        manifests = {m["id"]: m for m in list_manifests()}
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2
    if a.list:
        print(f"{'dataset':24} {'use':32} {'pack':6} {'estimate':>10}  categories")
        for m in manifests.values():
            print(f"{m['id']:24} {m['use']:32} {'yes' if m.get('pack') else 'no':6} {_est(m):>10}  "
                  f"{', '.join(m['categories'])}")
        return 0
    if a.all:
        ids = [i for i, m in manifests.items() if m.get("pack") and m["use"] in FETCHABLE
               and (m["use"] == "allowed" or a.accept_eval_only)]
    else:
        ids = a.datasets
    if not ids:
        ap.print_usage()
        return 1
    passwords = {}
    for item in a.archive_password:
        ds_name, sep, value = item.partition("=")
        if not sep or not value:
            print("--archive-password needs DATASET=PASSWORD", file=sys.stderr)
            return 1
        passwords[ds_name.strip()] = value
    root = data_root(a.data_dir)
    results: list[Result] = []
    failures: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for ds in ids:
        if ds not in manifests:
            failures[ds] = "no manifest"
            continue
        print(f"== {ds}", flush=True)
        try:
            r = fetch_dataset(manifests[ds], data_root=root, lock_dir=Path(a.lock_dir), splits_dir=Path(a.splits_dir),
                              accept_eval_only=a.accept_eval_only, update_lock=a.update_lock,
                              max_whole_bytes=int(a.max_whole_gb * 1e9),
                              log=lambda s: print(s, flush=True), passwords=passwords)
            print(f"{ds}: {r.split_status}; {r.lock_status}; {r.fetched_files} files fetched, "
                  f"{r.reused_files} already present", flush=True)
            results.append(r)
        except PackSkipped as exc:
            print(str(exc), flush=True)
            skipped[ds] = "archive password not given (see the message above)"
        except (PackRefused, FetchError, LockError, SplitMismatch, UnsafePath, ValueError, OSError) as exc:
            failures[ds] = str(exc)
    print()
    print(summary(results, failures, skipped))
    if any(r.split_status == "frozen split written" or r.lock_status.startswith("lock written") for r in results):
        print("\nNew files to commit (IDs and hashes only): "
              "eval/splits/<dataset>.json and eval/locks/<dataset>.lock.json")
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
