"""Build and read the page index: which pages exist, their category, split, GT file and image.

``prepare`` applies the split rule to a downloaded dataset, checks the result against the frozen
list in ``eval/splits/<dataset>.json`` (or writes it with ``write_splits=True``), converts the
chosen pages to ``iris-gt/1`` under ``<data>/gt/<dataset>/<split>/`` and writes
``<data>/index/<dataset>.jsonl``. It prints counts only, never document content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .datasets import get_converter
from .gt import GT_SCHEMA, parse_gt
from .manifests import load_manifest
from .paths import SPLITS_DIR, data_dir, gt_dir, index_path, raw_dir, safe_key
from .splits import SplitMismatch, check_frozen, compute_splits, frozen_record

__all__ = ["IndexEntry", "SplitMismatch", "check_frozen", "compute_splits", "frozen_record", "load_index", "prepare"]


@dataclass(frozen=True)
class IndexEntry:
    id: str
    key: str
    dataset: str
    category: str
    split: str
    gt_path: Path
    image: str
    private: bool = False


def prepare(dataset: str, write_splits: bool = False, splits_dir: Path = SPLITS_DIR) -> dict[str, Any]:
    manifest = load_manifest(dataset)
    if manifest["use"] == "excluded":
        raise PermissionError(f"{dataset} is excluded: {manifest.get('use_reason', '')}")
    conv = get_converter(manifest.get("converter"))
    raw = raw_dir(dataset)
    pages = conv.list_pages(raw)
    page_groups = getattr(conv, "page_groups", None)
    groups = page_groups(raw) if callable(page_groups) else None
    splits = compute_splits(manifest, pages, groups)
    status = check_frozen(frozen_record(manifest, splits), splits_dir, write_splits)

    out_entries: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    for cat, s in splits.items():
        for split in ("dev", "heldout"):
            d = gt_dir(dataset) / split
            d.mkdir(parents=True, exist_ok=True)
            for nid in s[split]:
                g = conv.convert(raw, nid)
                gt = {"schema": GT_SCHEMA, "id": f"{dataset}/{nid}", "dataset": dataset,
                      "category": cat, "split": split, **g}
                parse_gt(gt)
                key = safe_key(nid)
                p = d / f"{key}.gt.json"
                with p.open("w", encoding="utf-8") as f:
                    json.dump(gt, f, ensure_ascii=False)
                out_entries.append({"id": gt["id"], "key": key, "dataset": dataset, "category": cat,
                                    "split": split, "gt": str(p), "image": g["image"]})
            counts.setdefault(cat, {})[split] = len(s[split])
    ip = index_path(dataset)
    ip.parent.mkdir(parents=True, exist_ok=True)
    with ip.open("w", encoding="utf-8") as f:
        for e in out_entries:
            f.write(json.dumps(e) + "\n")
    return {"dataset": dataset, "available_pages": len(pages), "split_status": status, "counts": counts}


def _resolve(p: str) -> Path:
    """Index paths may be relative to the data directory (a dev export, eval/export_dev.py)."""
    path = Path(p)
    return path if path.is_absolute() else data_dir() / path


def load_index(dataset: str) -> list[IndexEntry]:
    p = index_path(dataset)
    if not p.is_file():
        raise FileNotFoundError(f"no index for {dataset}; run prepare first")
    out = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            out.append(IndexEntry(e["id"], e["key"], e["dataset"], e["category"], e["split"],
                                  _resolve(e["gt"]), str(_resolve(e["image"]))))
    return out
