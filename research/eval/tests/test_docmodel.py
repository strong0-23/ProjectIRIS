import pytest

from conftest import doc, para, word
from iris_eval.docmodel import DocModelError, parse_document


def test_blocks_follow_order_field() -> None:
    p = parse_document(doc(para("second", order=1), para("first", order=0)))
    assert [ln.text for ln in p.lines] == ["first", "second"]


def test_table_block_without_lines_gives_cells_row_major() -> None:
    table = {"type": "table", "table": {"cells": [
        {"row": 1, "col": 0, "text": "c"}, {"row": 0, "col": 1, "text": "b"},
        {"row": 0, "col": 0, "text": "a", "flags": ["low-confidence"]},
    ]}, "confidence": 0.8}
    p = parse_document(doc(table))
    assert [ln.text for ln in p.lines] == ["a", "b", "c"]
    assert len(p.tables) == 1
    cell_a = [c for c in p.tables[0].cells if c.text == "a"][0]
    assert cell_a.flagged and cell_a.confidence == 0.8


def test_flag_and_confidence_inheritance() -> None:
    b = para([word("x", conf=None), word("y", conf=0.2)], flags=["readers-disagree"])
    b["confidence"] = 0.7
    p = parse_document(doc(b))
    ws = p.lines[0].words
    assert ws[0].confidence == 0.7 and ws[0].flagged
    assert ws[1].confidence == 0.2


def test_pairs_and_cost() -> None:
    kv = {"type": "keyValue", "pairs": [{"key": {"text": "Total"}, "value": {"text": "9.90"}, "field": "total",
                                         "confidence": 0.9}]}
    src = {"timings": {"totalSeconds": 1.5}, "peakMemoryBytes": 1000,
           "models": [{"name": "m", "sizeBytes": 42}], "confidenceThreshold": 0.6}
    p = parse_document(doc(kv, source=src))
    assert p.pairs[0].key == "Total" and p.pairs[0].value == "9.90" and p.pairs[0].field == "total"
    assert [ln.text for ln in p.lines] == ["Total 9.90"]
    assert p.cost.seconds == 1.5 and p.cost.peak_memory_bytes == 1000 and p.cost.models == {"m": 42}
    assert p.declared_threshold == 0.6


def test_rejects_non_document() -> None:
    with pytest.raises(DocModelError):
        parse_document({"text": "plain"})
