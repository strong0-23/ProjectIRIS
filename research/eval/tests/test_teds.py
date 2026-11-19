import pytest

from iris_eval.gt import Cell, Table
from iris_eval.teds import match_tables, table_from_html, teds


def grid(rows: list[list[str]]) -> Table:
    return Table(tuple(Cell(r, c, 1, 1, t) for r, row in enumerate(rows) for c, t in enumerate(row)))


def test_identical_table() -> None:
    t = grid([["a", "b"], ["c", "d"]])
    assert teds(t, t) == 1.0


def test_one_cell_text_wrong() -> None:
    gt = grid([["a", "b"], ["c", "d"]])
    pred = grid([["a", "b"], ["c", "x"]])
    # 7 nodes (table, 2 tr, 4 td); one rename costing normalised Levenshtein("d", "x") = 1
    assert teds(gt, pred) == pytest.approx(1 - 1 / 7)
    assert teds(gt, pred, structure_only=True) == 1.0


def test_span_difference_costs_structure() -> None:
    gt = Table((Cell(0, 0, 1, 2, "h"), Cell(1, 0, 1, 1, "a"), Cell(1, 1, 1, 1, "b")))
    pred = grid([["h", ""], ["a", "b"]])
    # rename the colspan=2 cell (1) + insert one td (1); max nodes = 7
    assert teds(gt, pred) == pytest.approx(1 - 2 / 7)
    assert teds(gt, pred, structure_only=True) == pytest.approx(1 - 2 / 7)


def test_html_parsing_with_spans_and_inline_tags() -> None:
    html = (
        "<table><thead><tr><td rowspan=\"2\"><b>A</b></td><td colspan=\"2\">B</td></tr>"
        "<tr><td>c<sup>2</sup></td><td>d</td></tr></thead>"
        "<tbody><tr><td>e</td><td>f &amp; g</td><td></td></tr></tbody></table>"
    )
    t = table_from_html(html)
    got = [(c.row, c.col, c.row_span, c.col_span, c.text) for c in t.cells]
    assert got == [
        (0, 0, 2, 1, "A"),
        (0, 1, 1, 2, "B"),
        (1, 1, 1, 1, "c2"),
        (1, 2, 1, 1, "d"),
        (2, 0, 1, 1, "e"),
        (2, 1, 1, 1, "f & g"),
        (2, 2, 1, 1, ""),
    ]


def test_page_matching() -> None:
    t = grid([["a", "b"], ["c", "d"]])
    assert match_tables([], []).score is None
    assert match_tables([t], []).score == 0.0
    m = match_tables([t], [grid([["zz"]]), t])
    assert m.score == pytest.approx(0.5)
    assert m.pairs == [(0, 1)]
