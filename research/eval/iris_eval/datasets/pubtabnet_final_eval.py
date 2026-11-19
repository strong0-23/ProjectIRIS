"""PubTabNet final evaluation set (ICDAR 2021 Scientific Literature Parsing, task B).

Native layout after ``eval/download.py pubtabnet-final-eval``::

    raw/pubtabnet-final-eval/final_eval.json          {"<file>.png": {"html": "...", "type": ...}}
    raw/pubtabnet-final-eval/unpacked/final_eval.zip/  ... <file>.png

Each page is one table image. Ground truth: the table (cells, spans, text) from the HTML, and
the cell texts in row-major order as text lines. Inline tags such as ``<b>`` keep only their
text (the challenge also ignored ``b``). No key-values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..gt import table_to_json
from ..teds import table_from_html

CATEGORY = "tables"


class PubTabNetFinalEval:
    def __init__(self) -> None:
        self._gt: dict[str, Any] | None = None
        self._images: dict[str, Path] | None = None

    def _load(self, raw: Path) -> dict[str, Any]:
        if self._gt is None:
            with (raw / "final_eval.json").open(encoding="utf-8") as f:
                self._gt = json.load(f)
        return self._gt

    def _image(self, raw: Path, name: str) -> Path:
        if self._images is None:
            root = raw / "unpacked"
            self._images = {p.name: p for p in root.rglob("*.png")}
        if name not in self._images:
            raise FileNotFoundError(f"image {name} not found under {raw / 'unpacked'}")
        return self._images[name]

    def list_pages(self, raw: Path) -> list[tuple[str, str]]:
        return [(name, CATEGORY) for name in sorted(self._load(raw))]

    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        entry = self._load(raw)[native_id]
        table = table_from_html(entry["html"])
        lines = [c.text for c in sorted(table.cells, key=lambda c: (c.row, c.col))]
        return {
            "image": str(self._image(raw, native_id)),
            "conditions": [],
            "text": {"lines": lines, "reading_order": True},
            "tables": [table_to_json(table)],
            "pairs": None,
            "source_attributes": {"table_type": entry.get("type")},
        }
