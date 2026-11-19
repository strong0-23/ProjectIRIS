"""Apply the split rule to a downloaded dataset and convert its chosen pages to ``iris-gt/1``.

    python -m iris_eval.prepare pubtabnet-final-eval            # checks the frozen split
    python -m iris_eval.prepare pubtabnet-final-eval --write-splits   # first time only

Prints counts only.
"""

from __future__ import annotations

import argparse
import json
import sys

from .index import SplitMismatch, prepare


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset")
    ap.add_argument("--write-splits", action="store_true",
                    help="write eval/splits/<dataset>.json when it does not exist yet")
    a = ap.parse_args(argv)
    try:
        summary = prepare(a.dataset, write_splits=a.write_splits)
    except (SplitMismatch, PermissionError, KeyError, FileNotFoundError) as exc:
        print(f"prepare {a.dataset}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
