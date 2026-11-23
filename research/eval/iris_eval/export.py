"""Development-split export (``eval/export_dev.py``): one zip the owner can hand over (O6).

The zip mirrors a data directory, with paths relative to it, so unpacking it into an empty data
directory (``--import``) makes ``run_reader`` and ``score`` work on the dev split there::

    EXPORT.json                       iris-dev-export/1: datasets, licence use, page counts
    index/<dataset>.jsonl             dev entries only
    gt/<dataset>/dev/<key>.gt.json    iris-gt/1, "image" relative to the data directory
    images/<dataset>/<key>.<ext>

**Held-out pages are never in it.** Every page must be in the frozen dev list and not in the
frozen held-out list of its dataset, and its ground truth must say ``"split": "dev"``; anything
else stops the export. Private photos are included only with ``include_private`` and only those
assigned to dev (O7). Evaluation-only datasets need ``accept_eval_only``.
"""

from __future__ import annotations

import datetime as _dt
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .index import IndexEntry, load_index
from .manifests import EVAL_ONLY_USES, load_manifest
from .pack.safepath import safe_relpath
from .paths import SPLITS_DIR
from .private import load_private, read_private_gt
from .splits import frozen_ids

EXPORT_SCHEMA = "iris-dev-export/1"


class ExportError(RuntimeError):
    pass


@dataclass
class Item:
    dataset: str
    entry: IndexEntry
    gt: dict[str, Any]
    image_src: Path
    image_arc: str
    gt_arc: str

    @property
    def gt_bytes(self) -> bytes:
        return json.dumps(self.gt, ensure_ascii=False).encode("utf-8")


@dataclass
class Plan:
    items: list[Item]
    info: dict[str, Any]

    @property
    def size_bytes(self) -> int:
        return sum(i.image_src.stat().st_size + len(i.gt_bytes) for i in self.items)


def _item(ds: str, e: IndexEntry, gt: dict[str, Any]) -> Item:
    src = Path(e.image)
    if not src.is_file():
        raise ExportError(f"{e.id}: image not found")
    image_arc = safe_relpath(f"images/{ds}/{e.key}{src.suffix.lower()}")
    gt = {**gt, "image": image_arc}
    return Item(ds, e, gt, src, image_arc, safe_relpath(f"gt/{ds}/dev/{e.key}.gt.json"))


def plan_export(datasets: list[str], *, include_private: bool = False, accept_eval_only: bool = False,
                splits_dir: Path = SPLITS_DIR) -> Plan:
    items: list[Item] = []
    info: dict[str, Any] = {"schema": EXPORT_SCHEMA, "created": _dt.date.today().isoformat(), "split": "dev",
                            "datasets": {},
                            "note": "Development split only. Never commit, publish or redistribute (O4, O6, O7)."}
    for ds in datasets:
        m = load_manifest(ds)
        if m["use"] == "excluded":
            raise ExportError(f"{ds} is excluded")
        if m["use"] in EVAL_ONLY_USES and not accept_eval_only:
            raise ExportError(f"{ds} is evaluation-only; add --accept-eval-only to include it")
        frozen = frozen_ids(splits_dir, ds)
        if frozen is None:
            raise ExportError(f"{ds}: no frozen split; run fetch_pack / prepare first")
        n = 0
        for e in load_index(ds):
            if e.split != "dev":
                continue
            native = e.id.split("/", 1)[1]
            if native not in frozen["dev"] or native in frozen["heldout"]:
                raise ExportError(f"{e.id} is not in the frozen dev split of {ds}; export stopped")
            with e.gt_path.open(encoding="utf-8") as f:
                gt = json.load(f)
            if gt.get("split") != "dev":
                raise ExportError(f"{e.id}: ground truth is not marked dev; export stopped")
            items.append(_item(ds, e, gt))
            n += 1
        info["datasets"][ds] = {"use": m["use"], "dev_pages": n}
    if include_private:
        priv = load_private("dev")
        for e in priv:
            if e.split != "dev":
                raise ExportError("private page outside dev; export stopped")
            items.append(_item("private", e, read_private_gt(e)))
        info["datasets"]["private"] = {"use": "owner photos (O7)", "dev_pages": len(priv)}
    if any(i.gt.get("split") != "dev" for i in items):
        raise ExportError("held-out page in the export plan; export stopped")
    return Plan(items, info)


def write_export(plan: Plan, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    index: dict[str, list[str]] = {}
    with zipfile.ZipFile(tmp, "w") as z:
        for it in plan.items:
            z.write(it.image_src, it.image_arc, compress_type=zipfile.ZIP_STORED)
            z.writestr(it.gt_arc, it.gt_bytes, compress_type=zipfile.ZIP_DEFLATED)
            e = it.entry
            index.setdefault(it.dataset, []).append(json.dumps(
                {"id": e.id, "key": e.key, "dataset": it.dataset, "category": e.category, "split": "dev",
                 "gt": it.gt_arc, "image": it.image_arc}))
        for ds, lines in sorted(index.items()):
            z.writestr(f"index/{ds}.jsonl", "\n".join(lines) + "\n", compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("EXPORT.json", json.dumps(plan.info, indent=1), compress_type=zipfile.ZIP_DEFLATED)
    tmp.replace(out)
    return out


def import_export(archive: Path, data_root: Path) -> dict[str, Any]:
    """Unpack a dev export into ``data_root`` (refuses unsafe paths and anything not dev)."""
    with zipfile.ZipFile(archive) as z:
        info = json.loads(z.read("EXPORT.json"))
        if info.get("schema") != EXPORT_SCHEMA or info.get("split") != "dev":
            raise ExportError(f"{archive} is not an {EXPORT_SCHEMA} dev export")
        for zi in z.infolist():
            rel = safe_relpath(zi.filename)
            if not rel.startswith(("images/", "gt/", "index/")) and rel != "EXPORT.json":
                raise ExportError(f"unexpected member {zi.filename!r}")
            if rel.startswith("gt/") and "/dev/" not in rel:
                raise ExportError(f"non-dev ground truth {zi.filename!r}")
        for zi in z.infolist():
            target = data_root.joinpath(*safe_relpath(zi.filename).split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(zi))
    info_out: dict[str, Any] = info
    return info_out
