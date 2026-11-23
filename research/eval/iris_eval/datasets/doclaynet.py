"""DocLayNet test pages (PNG from the core archive, PDF text cells from the extra archive).

Text ground truth = the PDF text cells (``cells[].text``), sorted top to bottom then left to
right; DocLayNet gives no reading order, so none is claimed. A page whose PDF has no text layer
(no cells) has no text ground truth (``text: null``) rather than an empty one. The layout boxes
are not used (``iris-gt/1`` has no layout field yet).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._pack import PackConverter, page


def doclaynet_lines(cells_json: dict[str, Any]) -> list[str] | None:
    cells = [c for c in cells_json.get("cells") or [] if str(c.get("text") or "").strip()]
    if not cells:
        return None

    def pos(c: dict[str, Any]) -> tuple[float, float]:
        b = c.get("bbox") or [0, 0, 0, 0]
        return (round(float(b[1]), 1), float(b[0]))

    return [" ".join(str(c["text"]).split()) for c in sorted(cells, key=pos)]


class DocLayNet(PackConverter):
    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        cells = self.read_json(raw, native_id, "cells")
        return page(self.file(raw, native_id, "image"), lines=doclaynet_lines(cells), conditions=["born-digital"],
                    attrs=self.attrs(raw, native_id))
