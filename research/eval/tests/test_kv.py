from iris_eval.gt import Pair
from iris_eval.kv import score_pairs, visible


def test_visible_rule() -> None:
    assert visible(0.4, False, 0.5)
    assert visible(0.9, True, 0.5)
    assert not visible(0.9, False, 0.5)
    assert not visible(None, False, 0.5)


def test_field_match_and_silent_wrong_value() -> None:
    gt = [Pair(None, "total", "12.50"), Pair(None, "date", "01/02/2026")]
    pred = [Pair("TOTAL", "total", "12.80", 0.95), Pair("Date", "date", "01/02/2026", 0.9)]
    s = score_pairs(gt, pred, 0.5)
    assert s.correct == 1 and s.accuracy == 0.5
    assert s.wrong_values == 1 and s.silent_wrong_values == 1
    assert s.precision == 0.5


def test_flagged_wrong_value_is_not_silent() -> None:
    gt = [Pair(None, "total", "12.50")]
    pred = [Pair(None, "total", "12.80", 0.95, flagged=True)]
    s = score_pairs(gt, pred, 0.5)
    assert s.wrong_values == 1 and s.silent_wrong_values == 0


def test_key_text_similarity() -> None:
    gt = [Pair("Total:", None, "12.50")]
    assert score_pairs(gt, [Pair("TOTAL", None, "12.50", 0.9)], 0.5).correct == 1
    assert score_pairs(gt, [Pair("Subtotal amount", None, "12.50", 0.9)], 0.5).correct == 0


def test_value_only_match_and_empty() -> None:
    assert score_pairs([Pair(None, None, "x")], [Pair("anything", None, "x")], 0.5).correct == 1
    s = score_pairs([], [], 0.5)
    assert s.accuracy is None and s.precision is None
