"""The private slot: the owner's own documents, outside the repository.

``OCR_PRIVATE_DATA`` points at a folder laid out like this::

    $OCR_PRIVATE_DATA/
      dev/<category>/<page id>.<png|jpg|jpeg|tif|tiff|webp>
      dev/<category>/<page id>.gt.json
      heldout/<category>/...

Each ``.gt.json`` follows ``iris-gt/1``; ``id``, ``dataset``, ``category``, ``split`` and
``image`` may be left out and are filled in from the path (dataset ``private``). The owner
chooses the split by folder. Pages are scored like public ones; results carry only the page ID
and numbers, never text (that holds for every dataset).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .gt import GT_SCHEMA, SPLITS, parse_gt
from .index import IndexEntry
from .paths import PRIVATE_ENV, safe_key

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")


class PrivateDataError(RuntimeError):
    pass


def private_root() -> Path | None:
    v = os.environ.get(PRIVATE_ENV)
    return Path(v).resolve() if v else None


def load_private(split: str, root: Path | None = None) -> list[IndexEntry]:
    """Index the private pages of one split, filling in GT fields from the path."""
    if split not in SPLITS:
        raise ValueError(split)
    root = root or private_root()
    if root is None:
        return []
    base = root / split
    if not base.is_dir():
        return []
    out: list[IndexEntry] = []
    for cat_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for gt_file in sorted(cat_dir.glob("*.gt.json")):
            page = gt_file.name[: -len(".gt.json")]
            images = [cat_dir / f"{page}{s}" for s in IMAGE_SUFFIXES if (cat_dir / f"{page}{s}").is_file()]
            if not images:
                raise PrivateDataError(f"private page {split}/{cat_dir.name}/{page} has no image")
            out.append(
                IndexEntry(
                    id=f"private/{cat_dir.name}/{page}",
                    key=safe_key(f"{cat_dir.name}__{page}"),
                    dataset="private",
                    category=cat_dir.name,
                    split=split,
                    gt_path=gt_file,
                    image=str(images[0]),
                    private=True,
                )
            )
    return out


def read_private_gt(entry: IndexEntry) -> dict[str, object]:
    with entry.gt_path.open(encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("schema", GT_SCHEMA)
    d["id"] = entry.id
    d["dataset"] = "private"
    d["category"] = entry.category
    d["split"] = entry.split
    d["image"] = entry.image
    parse_gt(d)
    return dict(d)
