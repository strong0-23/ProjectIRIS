"""Run a candidate reader over the pages of one split and write its predictions.

    python -m iris_eval.run_reader --reader tesseract --dataset pubtabnet-final-eval \
        --split dev --out eval/.data/runs/tesseract-dev/predictions

Writes ``<out>/<dataset>/<key>.json`` (one IRIS document per page) and ``<out>/run.json``.
Held-out pages are refused without ``--heldout-scoring-run`` (E2). A page the reader fails on
gets no prediction file and is scored as empty output; the failure count is printed and recorded.
Only counts are printed, never document content.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .readers import get_reader
from .score import HELDOUT_FLAG, collect_entries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reader", required=True)
    ap.add_argument("--dataset", action="append", default=[])
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--split", choices=["dev", "heldout"], default="dev")
    ap.add_argument(HELDOUT_FLAG, action="store_true", dest="heldout_ok")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None, help="first N pages only (smoke tests)")
    a = ap.parse_args(argv)
    if a.split == "heldout" and not a.heldout_ok:
        print(f"refusing to run on held-out without {HELDOUT_FLAG} (E2)", file=sys.stderr)
        return 2
    entries = collect_entries(a.dataset, a.private, a.split)
    if a.limit is not None:
        entries = entries[: a.limit]
    if not entries:
        print("no pages (prepare a dataset or set OCR_PRIVATE_DATA)", file=sys.stderr)
        return 1
    reader = get_reader(a.reader)
    failures = 0
    t0 = time.perf_counter()
    for i, e in enumerate(entries, 1):
        d = a.out / e.dataset
        d.mkdir(parents=True, exist_ok=True)
        try:
            doc = reader.read(Path(e.image))
        except Exception as exc:  # noqa: BLE001 - a failed page is recorded, never hidden
            failures += 1
            print(f"page {e.id if not e.private else e.key}: reader failed ({type(exc).__name__})",
                  file=sys.stderr)
            continue
        with (d / f"{e.key}.json").open("w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        if i % 25 == 0:
            print(f"{i}/{len(entries)} pages")
    run = {
        "reader": reader.describe(),
        "split": a.split,
        "datasets": a.dataset + (["private"] if a.private else []),
        "pages": len(entries),
        "failures": failures,
        "wall_seconds": time.perf_counter() - t0,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": {"platform": platform.platform(), "python": platform.python_version(),
                 "cpu_count": os.cpu_count()},
    }
    a.out.mkdir(parents=True, exist_ok=True)
    with (a.out / "run.json").open("w", encoding="utf-8") as f:
        json.dump(run, f, indent=1)
    print(f"{len(entries) - failures}/{len(entries)} pages read, {failures} failures -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
