"""Table scoring: TEDS (tree-edit-distance similarity, Zhong et al., ECCV 2020).

A table becomes the tree ``table -> tr (one per row) -> td (one per cell anchored in that row,
by column)``; each ``td`` carries its ``colspan``, ``rowspan`` and normalised text. APTED computes
the edit distance with PubTabNet's costs: insert/delete 1; rename 1 when tag or spans differ,
otherwise the normalised Levenshtein distance between the two cells' texts.

    TEDS = 1 - distance / max(nodes(gt), nodes(pred))

``teds_struct`` ignores cell text (structure only). Differences from the official PubTabNet
script: no ``thead``/``tbody`` nodes (the IRIS document model has no header flag yet) and text
is compared after ``iris-norm/1`` rather than as raw HTML tokens, so values are close to, but not
directly comparable with, published PubTabNet TEDS.

On a page, GT and predicted tables are matched greedily by TEDS; the page score is the sum over
matched pairs divided by max(#gt tables, #pred tables), so missing and extra tables score 0.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser

from apted import APTED, Config
from rapidfuzz.distance import Levenshtein

from .gt import Cell, Table
from .normalize import normalize_text


@dataclass
class _Node:
    tag: str
    colspan: int = 1
    rowspan: int = 1
    text: str = ""
    children: list[_Node] = field(default_factory=list)


class _TedsConfig(Config):  # type: ignore[misc]
    def __init__(self, structure_only: bool) -> None:
        self.structure_only = structure_only

    def rename(self, a: _Node, b: _Node) -> float:
        if a.tag != b.tag or a.colspan != b.colspan or a.rowspan != b.rowspan:
            return 1.0
        if a.tag == "td" and not self.structure_only:
            if not a.text and not b.text:
                return 0.0
            return float(Levenshtein.normalized_distance(a.text, b.text))
        return 0.0

    def children(self, node: _Node) -> list[_Node]:
        return node.children


def _tree(table: Table) -> tuple[_Node, int]:
    rows: dict[int, list[Cell]] = {}
    for c in table.cells:
        rows.setdefault(c.row, []).append(c)
    root = _Node("table")
    count = 1
    n_rows = max(rows) + 1 if rows else 0
    for r in range(n_rows):
        tr = _Node("tr")
        count += 1
        for c in sorted(rows.get(r, []), key=lambda c: c.col):
            tr.children.append(_Node("td", c.col_span, c.row_span, normalize_text(c.text)))
            count += 1
        root.children.append(tr)
    return root, count


def teds(gt: Table, pred: Table, structure_only: bool = False) -> float:
    t1, n1 = _tree(gt)
    t2, n2 = _tree(pred)
    dist = APTED(t1, t2, _TedsConfig(structure_only)).compute_edit_distance()
    return max(0.0, 1.0 - float(dist) / max(n1, n2))


@dataclass
class TableMatch:
    score: float | None
    score_struct: float | None
    pairs: list[tuple[int, int]]


def match_tables(gt: Sequence[Table], pred: Sequence[Table]) -> TableMatch:
    """Greedy one-to-one matching of tables on a page by TEDS."""
    if not gt and not pred:
        return TableMatch(None, None, [])
    scores = [[teds(g, p) for p in pred] for g in gt]
    cand = sorted(
        ((scores[i][j], i, j) for i in range(len(gt)) for j in range(len(pred))),
        key=lambda x: (-x[0], x[1], x[2]),
    )
    used_g: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[int, int]] = []
    total = 0.0
    for s, i, j in cand:
        if i in used_g or j in used_p:
            continue
        used_g.add(i)
        used_p.add(j)
        pairs.append((i, j))
        total += s
    denom = max(len(gt), len(pred))
    struct_total = sum(teds(gt[i], pred[j], structure_only=True) for i, j in pairs)
    return TableMatch(total / denom, struct_total / denom, sorted(pairs))


class _HtmlTableParser(HTMLParser):
    """Collect rows of cells (with spans and text) from the first-level table in HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[int, int, str]]] = []
        self._cell: list[str] | None = None
        self._span = (1, 1)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []
            self._span = (int(a.get("rowspan") or 1), int(a.get("colspan") or 1))
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            if not self.rows:
                self.rows.append([])
            self.rows[-1].append((self._span[0], self._span[1], "".join(self._cell)))
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def table_from_html(html: str) -> Table:
    """Parse an HTML table into grid cells. Inline tags (b, i, sup, sub...) keep only their text."""
    p = _HtmlTableParser()
    p.feed(html)
    occupied: set[tuple[int, int]] = set()
    cells: list[Cell] = []
    for r, row in enumerate(p.rows):
        col = 0
        for rowspan, colspan, text in row:
            while (r, col) in occupied:
                col += 1
            cells.append(Cell(r, col, rowspan, colspan, text))
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied.add((r + dr, col + dc))
            col += colspan
    return Table(tuple(cells))
