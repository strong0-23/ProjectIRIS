"""CORD v2 receipts (Hugging Face parquet shards, fetched whole by ``eval/fetch_pack.py``).

Page ID ``<shard>/<row>``. Each row has ``image`` (``{"bytes", "path"}``) and ``ground_truth``,
a JSON string with ``valid_line`` (words with quads and ``row_id``) and ``gt_parse`` (menu items,
sub-total and total fields). The converter writes the page image to ``raw/cord-v2/images/`` and
returns:

- text: words grouped into printed rows by ``row_id`` (top to bottom, left to right); no
  reading-order claim;
- pairs: every item's name, quantity, unit price and amount (key = item name), and the
  sub-total and total fields under canonical names (``subtotal``, ``tax``, ``service_charge``,
  ``discount``, ``total``, ``cash``, ``change`` ...), values as printed.

Needs pyarrow (imported only here).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._pack import PackConverter, page, pair

MENU_FIELDS = {"nm": "item_name", "cnt": "item_quantity", "unitprice": "item_unit_price", "price": "item_amount"}
SUB_TOTAL_FIELDS = {"subtotal_price": "subtotal", "discount_price": "discount", "service_price": "service_charge",
                    "othersvc_price": "other_charge", "tax_price": "tax", "etc": "other_charge"}
TOTAL_FIELDS = {"total_price": "total", "total_etc": "other_total", "cashprice": "cash", "changeprice": "change",
                "creditcardprice": "card", "emoneyprice": "e_money", "menutype_cnt": "item_type_count",
                "menuqty_cnt": "item_count"}


def _values(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [x for item in v for x in _values(item)]
    if isinstance(v, dict):
        return []
    return [str(v)]


def _as_list(v: Any) -> list[dict[str, Any]]:
    if isinstance(v, dict):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    return []


def cord_lines(gt: dict[str, Any]) -> list[str]:
    rows: dict[Any, list[tuple[float, float, str]]] = {}
    for n, vl in enumerate(gt.get("valid_line") or []):
        for w in vl.get("words") or []:
            text = str(w.get("text") or "").strip()
            if not text:
                continue
            q = w.get("quad") or {}
            x = float(q.get("x1", 0))
            y = (float(q.get("y1", 0)) + float(q.get("y3", q.get("y1", 0)))) / 2
            key = ("row", w["row_id"]) if w.get("row_id") is not None else ("line", n)
            rows.setdefault(key, []).append((x, y, text))
    ordered = sorted(rows.values(), key=lambda ws: sum(w[1] for w in ws) / len(ws))
    return [" ".join(t for _, _, t in sorted(ws)) for ws in ordered]


def cord_pairs(gt: dict[str, Any]) -> list[dict[str, Any]]:
    parse = gt.get("gt_parse") or {}
    out: list[dict[str, Any] | None] = []
    for item in _as_list(parse.get("menu")):
        names = _values(item.get("nm"))
        name = names[0] if names else None
        for k, field in MENU_FIELDS.items():
            for v in _values(item.get(k)):
                out.append(pair(None if k == "nm" else name, field, v))
    for section, fields in (("sub_total", SUB_TOTAL_FIELDS), ("total", TOTAL_FIELDS)):
        for block in _as_list(parse.get(section)):
            for k, field in fields.items():
                for v in _values(block.get(k)):
                    out.append(pair(None, field, v))
    return [p for p in out if p is not None]


def _ext(data: bytes, path: str | None) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    suffix = Path(path or "").suffix.lower()
    return suffix if suffix in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff") else ".img"


class CordV2(PackConverter):
    def __init__(self) -> None:
        super().__init__()
        self._tables: dict[Path, Any] = {}

    def _row(self, raw: Path, native_id: str) -> tuple[dict[str, Any], str]:
        import pyarrow.parquet as pq  # research-only dependency, needed for this dataset only

        shard_file = self.file(raw, native_id, "shard")
        if shard_file not in self._tables:
            self._tables[shard_file] = pq.read_table(shard_file, columns=["image", "ground_truth"])
        t = self._tables[shard_file]
        row = int(native_id.rsplit("/", 1)[1])
        if row >= t.num_rows:
            raise IndexError(f"{native_id}: shard has only {t.num_rows} rows")
        image = t.column("image")[row].as_py()
        gt = t.column("ground_truth")[row].as_py()
        return image, gt

    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        image, gt_text = self._row(raw, native_id)
        data = image["bytes"] if isinstance(image, dict) else image
        ext = _ext(data, image.get("path") if isinstance(image, dict) else None)
        out = raw / "images" / f"{native_id.replace('/', '_')}{ext}"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.is_file() or out.stat().st_size != len(data):
            out.write_bytes(data)
        gt = json.loads(gt_text)
        return page(out, lines=cord_lines(gt), pairs=cord_pairs(gt), conditions=["phone-photo"],
                    attrs={"shard": native_id.split("/")[0]})
