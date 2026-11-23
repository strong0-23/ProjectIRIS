"""OmniDocBench pages (English), from ``OmniDocBench.json``.

Per page, ``layout_dets`` are taken in their ``order``; elements with ``ignore: true`` and
non-text elements (figure, isolated equation, abandon) are left out. Text ground truth = each
element's text lines; a table contributes its cells row by row (as a reader's table does) and the
table itself (from its ``html``) for TEDS. Reading order is claimed when every element used has
an order. Inline formulas stay as the LaTeX the dataset gives.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..gt import table_to_json
from ..teds import table_from_html
from ._pack import PackConverter, page

NO_TEXT = {"figure", "equation_isolated", "abandon"}


def omnidoc_gt(item: dict[str, Any]) -> tuple[list[str], bool, list[dict[str, Any]]]:
    dets = [d for d in item.get("layout_dets") or [] if isinstance(d, dict) and not d.get("ignore")]
    dets = [d for d in dets if d.get("category_type") not in NO_TEXT]
    ordered = all(isinstance(d.get("order"), int) for d in dets)
    def order(d: dict[str, Any]) -> tuple[bool, int]:
        o = d.get("order")
        return (not isinstance(o, int), o if isinstance(o, int) else 0)

    dets.sort(key=order)
    lines: list[str] = []
    tables: list[dict[str, Any]] = []
    for d in dets:
        if d.get("category_type") == "table" and d.get("html"):
            t = table_from_html(str(d["html"]))
            tables.append(table_to_json(t))
            lines += [c.text for c in sorted(t.cells, key=lambda c: (c.row, c.col)) if c.text.strip()]
            continue
        lines += [ln.strip() for ln in str(d.get("text") or "").splitlines() if ln.strip()]
    return lines, ordered, tables


class OmniDocBench(PackConverter):
    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, dict[str, Any]] | None = None

    def _item(self, raw: Path, native_id: str) -> dict[str, Any]:
        if self._items is None:
            with self.file(raw, native_id, "gt").open(encoding="utf-8") as f:
                data = json.load(f)
            self._items = {}
            for it in data:
                path = str((it.get("page_info") or {}).get("image_path") or "").replace("\\", "/")
                self._items.setdefault(path.removeprefix("images/"), it)
        return self._items[native_id]

    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        item = self._item(raw, native_id)
        lines, ordered, tables = omnidoc_gt(item)
        attr = (item.get("page_info") or {}).get("page_attribute") or {}
        conditions = [c for c, k in (("fuzzy-scan", "fuzzy_scan"), ("watermark", "watermark"),
                                     ("colourful-background", "colorful_backgroud")) if attr.get(k) is True]
        return page(self.file(raw, native_id, "image"), lines=lines, reading_order=ordered, tables=tables,
                    conditions=conditions, attrs={"data_source": attr.get("data_source")})
