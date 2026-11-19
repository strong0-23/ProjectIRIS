"""Ground truth in the IRIS page-GT format (``iris-gt/1``), one JSON file per page.

```
{
  "schema": "iris-gt/1",
  "id": "<dataset>/<native page id>",
  "dataset": "...", "category": "...", "split": "dev" | "heldout",
  "image": "<path to the page image>",
  "conditions": ["crumpled", "low-light", ...],
  "text":   {"lines": ["..."], "reading_order": true} | null,
  "tables": [{"cells": [{"row", "col", "rowSpan", "colSpan", "text"}]}] | null,
  "pairs":  [{"key": "..." | null, "field": "..." | null, "value": "..."}] | null
}
```

``null`` means "not annotated": that metric is not scored for the page. An empty list means
"annotated, and there are none".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GT_SCHEMA = "iris-gt/1"
SPLITS = ("dev", "heldout")


@dataclass(frozen=True)
class Cell:
    row: int
    col: int
    row_span: int
    col_span: int
    text: str
    confidence: float | None = None
    flagged: bool = False


@dataclass(frozen=True)
class Table:
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class Pair:
    key: str | None
    field: str | None
    value: str
    confidence: float | None = None
    flagged: bool = False


@dataclass
class PageGT:
    id: str
    dataset: str
    category: str
    split: str
    image: str
    conditions: list[str] = field(default_factory=list)
    lines: list[str] | None = None
    reading_order: bool = False
    tables: list[Table] | None = None
    pairs: list[Pair] | None = None


class GTError(ValueError):
    """Raised when a ground-truth file does not follow ``iris-gt/1``."""


def _cell(d: dict[str, Any]) -> Cell:
    return Cell(
        row=int(d["row"]),
        col=int(d["col"]),
        row_span=int(d.get("rowSpan", 1)),
        col_span=int(d.get("colSpan", 1)),
        text=str(d.get("text", "")),
    )


def parse_gt(d: dict[str, Any]) -> PageGT:
    """Validate and parse one page-GT object."""
    if d.get("schema") != GT_SCHEMA:
        raise GTError(f"expected schema {GT_SCHEMA!r}, got {d.get('schema')!r}")
    for key in ("id", "dataset", "category", "split", "image"):
        if not isinstance(d.get(key), str) or not d[key]:
            raise GTError(f"missing or empty field {key!r}")
    if d["split"] not in SPLITS:
        raise GTError(f"split must be one of {SPLITS}, got {d['split']!r}")
    text = d.get("text")
    lines: list[str] | None = None
    reading_order = False
    if text is not None:
        if not isinstance(text.get("lines"), list):
            raise GTError("text.lines must be a list")
        lines = [str(x) for x in text["lines"]]
        reading_order = bool(text.get("reading_order", False))
    tables = None
    if d.get("tables") is not None:
        tables = [Table(tuple(_cell(c) for c in t["cells"])) for t in d["tables"]]
    pairs = None
    if d.get("pairs") is not None:
        pairs = [
            Pair(key=p.get("key"), field=p.get("field"), value=str(p["value"]))
            for p in d["pairs"]
        ]
    return PageGT(
        id=d["id"],
        dataset=d["dataset"],
        category=d["category"],
        split=d["split"],
        image=d["image"],
        conditions=[str(c) for c in d.get("conditions", [])],
        lines=lines,
        reading_order=reading_order,
        tables=tables,
        pairs=pairs,
    )


def load_gt(path: Path) -> PageGT:
    with path.open(encoding="utf-8") as f:
        return parse_gt(json.load(f))


def table_to_json(t: Table) -> dict[str, Any]:
    return {
        "cells": [
            {"row": c.row, "col": c.col, "rowSpan": c.row_span, "colSpan": c.col_span, "text": c.text}
            for c in t.cells
        ]
    }
