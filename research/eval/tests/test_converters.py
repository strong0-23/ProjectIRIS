"""Converters to iris-gt/1, on synthetic native records shaped like each dataset's documented format."""

from __future__ import annotations

from iris_eval.datasets.cord_v2 import cord_lines, cord_pairs
from iris_eval.datasets.doclaynet import doclaynet_lines
from iris_eval.datasets.fatura import fatura_gt
from iris_eval.datasets.funsd import funsd_gt
from iris_eval.datasets.omnidocbench import omnidoc_gt
from iris_eval.datasets.tabrecset import parse_label, tabrecset_tables
from iris_eval.gt import parse_gt


def _valid(**parts: object) -> None:
    parse_gt({"schema": "iris-gt/1", "id": "d/p", "dataset": "d", "category": "receipts", "split": "dev",
              "image": "x.png", **parts})


def test_cord_rows_and_fields() -> None:
    gt = {
        "valid_line": [
            {"words": [{"text": "2", "row_id": 7, "quad": {"x1": 50, "y1": 10, "y3": 14}},
                       {"text": "NASI", "row_id": 7, "quad": {"x1": 0, "y1": 10, "y3": 14}}]},
            {"words": [{"text": "TOTAL", "row_id": 9, "quad": {"x1": 0, "y1": 40, "y3": 44}},
                       {"text": "", "row_id": 9, "quad": {"x1": 9, "y1": 40, "y3": 44}}]},
            {"words": [{"text": "SHOP", "quad": {"x1": 0, "y1": 1, "y3": 3}}]},
        ],
        "gt_parse": {"menu": {"nm": "NASI", "cnt": "2", "price": ["20,000", "1"]},
                     "sub_total": {"subtotal_price": "20,000", "tax_price": "2,000"},
                     "total": {"total_price": "22,000", "cashprice": "50,000", "changeprice": "28,000"}},
    }
    assert cord_lines(gt) == ["SHOP", "NASI 2", "TOTAL"]
    pairs = cord_pairs(gt)
    assert {"key": "NASI", "field": "item_amount", "value": "20,000"} in pairs
    assert {"key": "NASI", "field": "item_amount", "value": "1"} in pairs
    assert {"key": None, "field": "item_name", "value": "NASI"} in pairs
    assert {"key": None, "field": "tax", "value": "2,000"} in pairs
    assert {"key": None, "field": "change", "value": "28,000"} in pairs
    _valid(text={"lines": cord_lines(gt)}, pairs=pairs)
    assert cord_pairs({}) == [] and cord_lines({}) == []


def test_doclaynet_cells_sorted_and_empty_page_is_not_annotated() -> None:
    cells = {"cells": [{"bbox": [300, 100, 10, 10], "text": "b"}, {"bbox": [10, 100, 10, 10], "text": "a"},
                       {"bbox": [0, 5, 1, 1], "text": "  title  "}, {"bbox": [0, 0, 1, 1], "text": " "}]}
    assert doclaynet_lines(cells) == ["title", "a", "b"]
    assert doclaynet_lines({"cells": []}) is None
    assert doclaynet_lines({}) is None


def test_fatura_regions_fields_and_labels() -> None:
    ann = {"TITLE": {"bbox": [1], "text": "INVOICE"},
           "DATE": {"bbox": [1], "text": "Date: 20-Mar-2008"},
           "TOTAL": {"bbox": [1], "text": "TOTAL 123.00 EUR"},
           "SELLER NAME": {"bbox": [1], "text": "Synthetic Co"},
           "TABLE": [{"bbox": [1], "text": "Item Qty\nWidget 2"}],
           "LOGO": {"bbox": [1]}}
    lines, pairs = fatura_gt(ann)
    assert lines == ["INVOICE", "Date: 20-Mar-2008", "TOTAL 123.00 EUR", "Synthetic Co", "Item Qty", "Widget 2"]
    assert {"key": "Date", "field": "date", "value": "20-Mar-2008"} in pairs
    assert {"key": None, "field": "total", "value": "TOTAL 123.00 EUR"} in pairs
    assert {"key": None, "field": "seller_name", "value": "Synthetic Co"} in pairs
    assert len(pairs) == 3
    _valid(text={"lines": lines}, pairs=pairs)


def test_tabrecset_labels_tables_and_reindexing() -> None:
    assert parse_label("3-2-1-1-a-b - c") == (3, 2, 1, 1, "a-b - c")
    assert parse_label("2-1-1-1") == (2, 1, 1, 1, "")
    assert parse_label("table") is None and parse_label("x-1-1-1-y") is None
    ann = {"shapes": [{"label": "1-1-1-2-Head", "group_id": 0}, {"label": "2-1-1-1-a", "group_id": 0},
                      {"label": "2-2-1-1-b", "group_id": 0}, {"label": "1-1-1-1-solo", "group_id": 1},
                      {"label": "table", "group_id": 0}]}
    tables = tabrecset_tables(ann)
    assert len(tables) == 2
    assert tables[0]["cells"][0] == {"row": 0, "col": 0, "rowSpan": 1, "colSpan": 2, "text": "Head"}
    assert [c["text"] for c in tables[0]["cells"]] == ["Head", "a", "b"]
    _valid(tables=tables)


def test_funsd_links_question_to_answer_either_direction() -> None:
    ann = {"form": [
        {"id": 0, "text": "Date:", "label": "question", "box": [0, 10, 5, 12], "linking": [[0, 1]]},
        {"id": 1, "text": "1/2/99", "label": "answer", "box": [6, 10, 9, 12], "linking": [[0, 1]]},
        {"id": 2, "text": "To", "label": "question", "box": [0, 20, 5, 22], "linking": [[3, 2]]},
        {"id": 3, "text": "Someone", "label": "answer", "box": [6, 20, 9, 22], "linking": [[3, 2]]},
        {"id": 4, "text": "FORM", "label": "header", "box": [0, 0, 9, 2], "linking": [[4, 0]]},
        {"id": 5, "text": "", "label": "answer", "box": [0, 30, 1, 31], "linking": [[2, 5]]},
    ]}
    lines, pairs = funsd_gt(ann)
    assert lines == ["FORM", "Date:", "1/2/99", "To", "Someone"]
    assert pairs == [{"key": "Date:", "field": None, "value": "1/2/99"},
                     {"key": "To", "field": None, "value": "Someone"}]
    _valid(text={"lines": lines}, pairs=pairs)


def test_omnidocbench_order_ignore_and_tables() -> None:
    item = {"layout_dets": [
        {"category_type": "text_block", "order": 2, "text": "second para\nline 2"},
        {"category_type": "title", "order": 0, "text": "Title"},
        {"category_type": "table", "order": 1,
         "html": "<table><tr><td>h1</td><td>h2</td></tr><tr><td>1</td><td>2</td></tr></table>"},
        {"category_type": "figure", "order": 3},
        {"category_type": "header", "order": 4, "text": "ignored header", "ignore": True},
        {"category_type": "equation_isolated", "order": 5, "latex": "x^2"},
    ]}
    lines, ordered, tables = omnidoc_gt(item)
    assert lines == ["Title", "h1", "h2", "1", "2", "second para", "line 2"]
    assert ordered is True and len(tables) == 1 and len(tables[0]["cells"]) == 4
    lines2, ordered2, _ = omnidoc_gt({"layout_dets": [{"category_type": "text_block", "text": "x"}]})
    assert lines2 == ["x"] and ordered2 is False
    _valid(text={"lines": lines, "reading_order": ordered}, tables=tables)
