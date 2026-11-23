#!/usr/bin/env python3
"""Export the development split (images and ground truth) into one zip, held-out never included.

    python eval/export_dev.py --accept-eval-only                 # prepare, estimate, write the zip
    python eval/export_dev.py --dry-run                          # size estimate only
    python eval/export_dev.py --import iris-dev.zip --data-dir <empty folder>   # on the receiving side

By default every fetched dataset is prepared first (``iris_eval.prepare``: converts the split's
pages to ground truth and checks the frozen split), then its dev pages are exported. The size is
printed before anything is written. Private photos (O7) are added only with
``--include-private``, and only those assigned to dev.

Needs the harness requirements (``pip install -r research/eval/requirements.txt``).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "research" / "eval"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", action="append", default=[], help="dataset id (repeatable); default: all fetched")
    ap.add_argument("--accept-eval-only", action="store_true", help="include datasets approved for evaluation only")
    ap.add_argument("--include-private", action="store_true", help="include your own dev photos (OCR_PRIVATE_DATA)")
    ap.add_argument("--data-dir")
    ap.add_argument("--splits-dir", default=str(HERE / "splits"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="print the size estimate and stop")
    ap.add_argument("--no-prepare", action="store_true", help="export what is already prepared")
    ap.add_argument("--import", dest="import_zip", type=Path, help="unpack a dev export into --data-dir")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows consoles: never crash on a file name
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    if a.data_dir:
        os.environ["IRIS_EVAL_DATA"] = str(Path(a.data_dir).resolve())

    from iris_eval.export import ExportError, import_export, plan_export, write_export
    from iris_eval.index import prepare
    from iris_eval.manifests import EVAL_ONLY_USES, list_manifests
    from iris_eval.paths import data_dir

    root = data_dir()
    if a.import_zip:
        try:
            info = import_export(a.import_zip, root)
        except (ExportError, OSError, ValueError) as exc:
            print(f"import: {exc}", file=sys.stderr)
            return 1
        print(f"imported into {root}: " + ", ".join(f"{d} {v['dev_pages']}" for d, v in info["datasets"].items()))
        return 0

    manifests = {m["id"]: m for m in list_manifests()}
    ids = a.dataset or [i for i, m in manifests.items() if m.get("converter") and (root / "raw" / i).is_dir()
                        and m["use"] != "excluded" and (m["use"] not in EVAL_ONLY_USES or a.accept_eval_only)]
    splits_dir = Path(a.splits_dir)
    failed = 0
    ready = []
    for ds in ids:
        if not a.no_prepare:
            try:
                s = prepare(ds, write_splits=False, splits_dir=splits_dir)
                print(f"{ds}: prepared ({s['split_status']}): "
                      + ", ".join(f"{c} {v.get('dev', 0)} dev" for c, v in s["counts"].items()))
            except Exception as exc:  # noqa: BLE001 - report and continue with the other datasets
                print(f"{ds}: not prepared: {exc}", file=sys.stderr)
                failed += 1
                continue
        ready.append(ds)
    try:
        plan = plan_export(ready, include_private=a.include_private, accept_eval_only=a.accept_eval_only,
                           splits_dir=splits_dir)
    except (ExportError, OSError, ValueError, KeyError) as exc:
        print(f"export: {exc}", file=sys.stderr)
        return 1
    for ds, v in plan.info["datasets"].items():
        print(f"  {ds:24} {v['dev_pages']:>5} dev pages  ({v['use']})")
    print(f"estimated zip size: {plan.size_bytes / 1e6:,.1f} MB for {len(plan.items)} pages")
    if a.dry_run:
        return 0 if not failed else 3
    out = a.out or root / "exports" / f"iris-dev-{_dt.date.today().isoformat()}.zip"
    write_export(plan, out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:,.1f} MB). Development split only; never commit or share it.")
    return 0 if not failed else 3


if __name__ == "__main__":
    raise SystemExit(main())
