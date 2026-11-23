"""BLN600: 19th-century newspaper article images with human transcriptions.

Text ground truth = the non-empty lines of ``Ground Truth/<id>.txt`` in their order (reading
order claimed). The machine OCR in ``OCR Text/`` is never used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._pack import PackConverter, page


class Bln600(PackConverter):
    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        return page(self.file(raw, native_id, "image"), lines=self.read_lines(raw, native_id, "text"),
                    reading_order=True, conditions=["old-print"])
