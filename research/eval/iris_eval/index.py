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
from .paths import SPLITS_DIR, gt_dir, index_path, raw_dir, safe_key
from .splits import SPLIT_RULE, list_digest, split_ids


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


class SplitMismatch(RuntimeError):
    pass


def compute_splits(manifest: dict[str, Any], pages: list[tuple[str, str]]) -> dict[str, dict[str, list[str]]]:
    sp = manifest["split"]
    if sp["rule"] != SPLIT_RULE:
        raise ValueError(f"unknown split rule {sp['rule']!r}")
    by_cat: dict[str, list[str]] = {}
    for nid, cat in pages:
        by_cat.setdefault(cat, []).append(nid)
    return {
        cat: split_ids(
            ids,
            seed=sp["seed"],
            dataset=manifest["id"],
            dev_fraction=float(sp["dev_fraction"]),
            sample=sp["sample_per_category"],
            exclude=sp["exclude"],
        )
        for cat, ids in sorted(by_cat.items())
    }


def frozen_record(manifest: dict[str, Any], splits: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    sp = manifest["split"]
    return {
        "dataset": manifest["id"],
        "rule": sp["rule"],
        "seed": sp["seed"],
        "dev_fraction": sp["dev_fraction"],
        "sample_per_category": sp["sample_per_category"],
        "excluded_ids": len(sp["exclude"]),
        "categories": {
            cat: {
                "dev": s["dev"],
                "heldout": s["heldout"],
                "dev_sha256": list_digest(s["dev"]),
                "heldout_sha256": list_digest(s["heldout"]),
            }
            for cat, s in splits.items()
        },
    }


def check_frozen(record: dict[str, Any], splits_dir: Path, write: bool) -> str:
    path = splits_dir / f"{record['dataset']}.json"
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            frozen = json.load(f)
        if frozen != record:
            raise SplitMismatch(
                f"{path} differs from the split recomputed from the manifest and data; "
                "the data or the manifest changed. Do not overwrite without an orchestrator decision."
            )
        return "matches frozen split"
    if not write:
        raise SplitMismatch(f"no frozen split {path}; run prepare with --write-splits once")
    splits_dir.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=1)
        f.write("\n")
    return "frozen split written"


def prepare(dataset: str, write_splits: bool = False, splits_dir: Path = SPLITS_DIR) -> dict[str, Any]:
    manifest = load_manifest(dataset)
    if manifest["use"] == "excluded":
        raise PermissionError(f"{dataset} is excluded: {manifest.get('use_reason', '')}")
    conv = get_converter(manifest.get("converter"))
    raw = raw_dir(dataset)
    pages = conv.list_pages(raw)
    splits = compute_splits(manifest, pages)
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


def load_index(dataset: str) -> list[IndexEntry]:
    p = index_path(dataset)
    if not p.is_file():
        raise FileNotFoundError(f"no index for {dataset}; run prepare first")
    out = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            out.append(IndexEntry(e["id"], e["key"], e["dataset"], e["category"], e["split"],
                                  Path(e["gt"]), e["image"]))
    return out
