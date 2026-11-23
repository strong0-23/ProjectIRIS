"""FATURA synthetic invoices (``Annotations/Original_Format/<id>.json``).

The original format maps a field class to a region: ``{"<CLASS>": {"bbox": [...], "text": "..."}}``
(a list of regions is accepted too). Text ground truth = the lines of every annotated region;
key-values = the short fields below, split at the first ``:`` of the first line into printed
label (key) and value when there is one. Classes such as TABLE, NOTE, CONDITIONS, LOGO and the
address blocks contribute text only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ._pack import PackConverter, page, pair

FIELDS = {"DATE": "date", "DUE_DATE": "due_date", "NUMBER": "invoice_number", "PO_NUMBER": "po_number",
          "TOTAL": "total", "SUB_TOTAL": "subtotal", "TAX": "tax", "GST": "gst", "DISCOUNT": "discount",
          "AMOUNT_DUE": "amount_due", "SELLER_EMAIL": "seller_email", "SELLER_SITE": "seller_site",
          "SELLER_NAME": "seller_name", "TOTAL_WORDS": "total_words"}


def _regions(v: Any) -> list[dict[str, Any]]:
    if isinstance(v, dict) and "text" in v:
        return [v]
    if isinstance(v, list):
        return [r for x in v for r in _regions(x)]
    return []


def _class(k: str) -> str:
    return re.sub(r"[\s\-]+", "_", k.strip().upper())


def fatura_gt(ann: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    lines: list[str] = []
    pairs: list[dict[str, Any]] = []
    for k, v in ann.items():
        for region in _regions(v):
            text = str(region.get("text") or "")
            rows = [r.strip() for r in text.splitlines() if r.strip()]
            lines += rows
            field = FIELDS.get(_class(k))
            if field and rows:
                head, sep, tail = rows[0].partition(":")
                if sep and tail.strip():
                    p = pair(head, field, " ".join([tail.strip(), *rows[1:]]))
                else:
                    p = pair(None, field, " ".join(rows))
                if p:
                    pairs.append(p)
    return lines, pairs


class Fatura(PackConverter):
    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        lines, pairs = fatura_gt(self.read_json(raw, native_id, "annotation"))
        return page(self.file(raw, native_id, "image"), lines=lines, pairs=pairs, conditions=["synthetic"],
                    attrs={"template": native_id.split("_")[0]})
