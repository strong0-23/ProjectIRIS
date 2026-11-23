"""SmartDoc 2015 Challenge 2: phone photos of printed pages, one UTF-8 text file per image.

Text ground truth = the non-empty lines of the text file, in document order (reading order is
claimed: the pages are single-column). Captures of one source document share a group, so the
split keeps them on one side (``iris-split/1-grouped``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._pack import PackConverter, page


class SmartDoc2015(PackConverter):
    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        return page(self.file(raw, native_id, "image"), lines=self.read_lines(raw, native_id, "text"),
                    reading_order=True, conditions=["phone-photo"])
