from conftest import doc, para, word
from iris_eval.docmodel import PredWord, parse_document
from iris_eval.gt import Cell, PageGT, Table
from iris_eval.score import score_page
from iris_eval.silent import cell_silent_errors, word_silent_errors


def W(t: str, c: float | None = 0.9, f: bool = False) -> PredWord:
    return PredWord(t, c, f)


def test_wrong_confident_number_is_silent() -> None:
    s = word_silent_errors(["Total", "12.50"], [W("Total"), W("12.80")], 0.5)
    assert (s.wrong_words, s.silent_words) == (1, 1)
    assert (s.gt_numbers, s.wrong_numbers, s.silent_numbers) == (1, 1, 1)


def test_low_confidence_wrong_word_is_visible() -> None:
    s = word_silent_errors(["Total", "12.50"], [W("Total"), W("12.80", 0.3)], 0.5)
    assert (s.wrong_words, s.silent_words, s.silent_numbers) == (1, 0, 0)


def test_flagged_wrong_word_is_visible() -> None:
    s = word_silent_errors(["Total", "12.50"], [W("Total"), W("12.80", 0.99, True)], 0.5)
    assert s.silent_words == 0 and s.wrong_numbers == 1


def test_false_flag_and_missed_and_inserted() -> None:
    s = word_silent_errors(["a", "b", "c"], [W("a", 0.2), W("c")], 0.5)
    assert s.false_flags == 1 and s.missed_words == 1 and s.wrong_words == 0
    s = word_silent_errors(["a"], [W("a"), W("99")], 0.5)
    assert s.wrong_words == 1 and s.wrong_numbers == 1 and s.silent_numbers == 1


def test_missing_confidence_counts_as_confident() -> None:
    s = word_silent_errors(["a"], [W("b", None)], 0.5)
    assert s.silent_words == 1


def grid(rows, conf=0.9, flagged=()):  # type: ignore[no-untyped-def]
    return Table(tuple(Cell(r, c, 1, 1, t, conf, (r, c) in flagged)
                       for r, row in enumerate(rows) for c, t in enumerate(row)))


def test_cells() -> None:
    gt = grid([["a", "b"], ["c", "d"]])
    pred = grid([["a", "x"], ["c", "y"]], flagged={(1, 1)})
    s = cell_silent_errors([gt], [pred], [(0, 0)], 0.5)
    assert (s.gt_cells, s.wrong_cells, s.silent_cells) == (4, 2, 1)
    extra = grid([["q", ""]])
    s = cell_silent_errors([gt], [pred, extra], [(0, 0)], 0.5)
    assert (s.wrong_cells, s.silent_cells) == (3, 2)


def test_block_flag_reaches_words_end_to_end() -> None:
    gt = PageGT("d/p", "d", "receipts", "dev", "img.png", lines=["Total 12.50"], reading_order=True)
    flagged = parse_document(doc(para([word("Total"), word("12.80")], flags=["low-confidence"])))
    rec = score_page(gt, flagged, 0.5)
    assert rec["silent"]["words"]["wrong_words"] == 1
    assert rec["silent"]["words"]["silent_words"] == 0
    unflagged = parse_document(doc(para([word("Total"), word("12.80")])))
    assert score_page(gt, unflagged, 0.5)["silent"]["words"]["silent_numbers"] == 1
