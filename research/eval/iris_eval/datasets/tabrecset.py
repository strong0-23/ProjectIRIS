"""TabRecSet English tables (labelme JSON in ``TSR_TCR_annotation``).

Each cell is a shape whose ``label`` encodes ``<row>-<column>-<rowspan>-<colspan>-<text>`` and
whose ``group_id`` names its table. Ground truth = the tables (structure and cell text). The
images hold only tables, but text outside the table is not annotated, so there is no page text
ground truth (``text: null``); tables are scored by TEDS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._pack import PackConverter, page, table_cells


def parse_label(label: str) -> tuple[int, int, int, int, str] | None:
    parts = str(label).split("-", 4)
    if len(parts) < 4:
        return None
    try:
        r, c, rs, cs = (int(x) for x in parts[:4])
    except ValueError:
        return None
    text = parts[4] if len(parts) == 5 else ""
    return r, c, rs, cs, " ".join(text.split())


def tabrecset_tables(ann: dict[str, Any]) -> list[dict[str, Any]]:
    by_table: dict[Any, list[tuple[int, int, int, int, str]]] = {}
    for shape in ann.get("shapes") or []:
        cell = parse_label(shape.get("label", ""))
        if cell is not None:
            by_table.setdefault(shape.get("group_id"), []).append(cell)
    return [table_cells(cells) for _, cells in sorted(by_table.items(), key=lambda kv: str(kv[0]))]


class TabRecSet(PackConverter):
    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        tables = tabrecset_tables(self.read_json(raw, native_id, "annotation"))
        return page(self.file(raw, native_id, "image"), lines=None, tables=tables, conditions=["in-the-wild"])
