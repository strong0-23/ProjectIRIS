import pytest

from conftest import doc, para
from iris_eval.docmodel import parse_document
from iris_eval.textmetrics import score_text


def lines_of(*texts: str):  # type: ignore[no-untyped-def]
    return parse_document(doc(para(*texts))).lines


def test_identical_is_perfect() -> None:
    ts = score_text(["hello world", "second line here"], lines_of("hello world", "second line here"), True)
    assert ts.cer == 0 and ts.wer == 0
    assert ts.cer_ordered == 0
    assert ts.order_score == 1.0


def test_one_substitution() -> None:
    ts = score_text(["hello world"], lines_of("hellp world"), False)
    assert ts.char_edits == 1
    assert ts.cer == pytest.approx(1 / 11)
    assert ts.word_edits == 1
    assert ts.wer == pytest.approx(0.5)
    assert ts.cer_ordered is None and ts.order_score is None


def test_text_is_order_independent_but_order_is_scored() -> None:
    gt = ["alpha beta gamma", "delta epsilon zeta"]
    ts = score_text(gt, lines_of("delta epsilon zeta", "alpha beta gamma"), True)
    assert ts.cer == 0
    assert ts.wer == 0
    assert ts.cer_ordered is not None and ts.cer_ordered > 0
    assert ts.order_score == 0.0


def test_line_breaks_do_not_cost() -> None:
    ts = score_text(["a b", "c"], lines_of("a", "b c"), False)
    assert ts.cer == 0


def test_empty_prediction() -> None:
    ts = score_text(["hello world"], [], True)
    assert ts.cer == 1.0 and ts.wer == 1.0
    assert ts.order_score is None


def test_unmatched_lines_go_last_as_insertions() -> None:
    ts = score_text(["hello world"], lines_of("zzzz qqqq", "hello world"), False)
    assert ts.char_edits == len(" zzzz qqqq")


def test_empty_ground_truth() -> None:
    ts = score_text([], lines_of("noise"), False)
    assert ts.cer is None and ts.gt_chars == 0


def test_text_cer_never_exceeds_reader_order_cer() -> None:
    gt = ["the quick brown fox", "jumps over the lazy dog", "and runs away"]
    noisy = lines_of("tha qu1ck brwn f0x", "jumps ovr th lazy", "dog and rns away", "xx")
    ts = score_text(gt, noisy, True)
    assert ts.cer is not None and ts.cer_ordered is not None
    assert ts.cer <= ts.cer_ordered
