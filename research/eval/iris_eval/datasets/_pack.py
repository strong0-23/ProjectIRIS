"""Base for converters of datasets fetched by ``eval/fetch_pack.py``.

The page list (IDs, categories, groups) comes from ``raw/<dataset>/pack.json``, the record the
fetch wrote, so ``prepare`` recomputes exactly the split the fetch used. Files are found through
the same record (``files[<page id>][<role>]``, relative to ``raw/<dataset>/``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..pack.safepath import as_path


class PackConverter:
    def __init__(self) -> None:
        self._pack: dict[str, Any] | None = None

    def pack(self, raw: Path) -> dict[str, Any]:
        if self._pack is None:
            p = raw / "pack.json"
            if not p.is_file():
                raise FileNotFoundError(f"{p} not found; run eval/fetch_pack.py for this dataset first")
            with p.open(encoding="utf-8") as f:
                self._pack = json.load(f)
        return self._pack

    def list_pages(self, raw: Path) -> list[tuple[str, str]]:
        return [(str(p["id"]), str(p["category"])) for p in self.pack(raw)["population"]]

    def page_groups(self, raw: Path) -> dict[str, str] | None:
        pop = self.pack(raw)["population"]
        if not pop or "group" not in pop[0]:
            return None
        return {str(p["id"]): str(p["group"]) for p in pop}

    def attrs(self, raw: Path, native_id: str) -> dict[str, Any]:
        for p in self.pack(raw)["population"]:
            if p["id"] == native_id:
                a: dict[str, Any] = p.get("attrs") or {}
                return a
        return {}

    def file(self, raw: Path, native_id: str, role: str) -> Path:
        files = self.pack(raw)["files"].get(native_id) or {}
        if role not in files:
            raise FileNotFoundError(f"page {native_id}: no {role} file in pack.json (not fetched)")
        return as_path(raw, files[role])

    def read_json(self, raw: Path, native_id: str, role: str) -> Any:
        with self.file(raw, native_id, role).open(encoding="utf-8") as f:
            return json.load(f)

    def read_lines(self, raw: Path, native_id: str, role: str) -> list[str]:
        """Non-empty lines of a UTF-8 text file (a BOM and trailing spaces are dropped)."""
        text = self.file(raw, native_id, role).read_text(encoding="utf-8-sig", errors="replace")
        return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


def page(image: Path | str, *, lines: list[str] | None, reading_order: bool = False,
         tables: list[dict[str, Any]] | None = None, pairs: list[dict[str, Any]] | None = None,
         conditions: list[str] | None = None, attrs: dict[str, Any] | None = None) -> dict[str, Any]:
    """The converter output for one page (``prepare`` adds schema, id, dataset, category, split)."""
    out: dict[str, Any] = {
        "image": str(image),
        "conditions": conditions or [],
        "text": None if lines is None else {"lines": lines, "reading_order": reading_order},
        "tables": tables,
        "pairs": pairs,
    }
    if attrs:
        out["source_attributes"] = attrs
    return out


def pair(key: str | None, field: str | None, value: object) -> dict[str, Any] | None:
    """A ground-truth key-value pair, or None when the value is empty."""
    v = "" if value is None else " ".join(str(value).split())
    if not v:
        return None
    k = None if key is None else (" ".join(str(key).split()) or None)
    return {"key": k, "field": field, "value": v}


def table_cells(cells: list[tuple[int, int, int, int, str]]) -> dict[str, Any]:
    """A table from (row, col, rowspan, colspan, text), re-indexed so rows and columns start at 0."""
    if not cells:
        return {"cells": []}
    r0 = min(c[0] for c in cells)
    c0 = min(c[1] for c in cells)
    return {"cells": [{"row": r - r0, "col": c - c0, "rowSpan": max(1, rs), "colSpan": max(1, cs), "text": t}
                      for r, c, rs, cs, t in sorted(cells, key=lambda x: (x[0], x[1]))]}
