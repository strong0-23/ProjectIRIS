from iris_eval.normalize import has_digit, normalize_text, words


def test_quotes_dashes_spaces_and_ellipsis() -> None:
    assert normalize_text("“Hello” —  world…") == '"Hello" - world...'


def test_ligature_zero_width_and_minus() -> None:
    assert normalize_text("ofﬁce​ −5") == "office -5"


def test_case_and_punctuation_kept() -> None:
    assert normalize_text("Total: RM 12.50") == "Total: RM 12.50"


def test_line_breaks_collapse() -> None:
    assert normalize_text("  a\n\tb  \r\n c ") == "a b c"


def test_words_and_digits() -> None:
    assert words("") == []
    assert words(" a  b ") == ["a", "b"]
    assert has_digit("RM12") and not has_digit("Total")
