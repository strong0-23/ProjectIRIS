"""Text normalisation applied to ground truth and predictions before any text comparison.

Version ``iris-norm/1``. The steps, in order:

1. Unicode NFKC (folds ligatures, full-width forms, compatibility spaces, "..." for the ellipsis).
2. Map typographic variants to ASCII: curly and prime quotes to ``'`` / ``"``, every dash and the
   minus sign to ``-``.
3. Drop zero-width and control characters (except whitespace).
4. Collapse every run of whitespace (including line breaks) to one space and trim.

Case, punctuation and diacritics are kept: a reader that drops them is making an error.
"""

from __future__ import annotations

import re
import unicodedata

NORMALISATION_VERSION = "iris-norm/1"

_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "´": "'",
        "`": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "″": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "﹣": "-",
        "－": "-",
    }
)

_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­]")
_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Return ``text`` normalised by ``iris-norm/1``."""
    s = unicodedata.normalize("NFKC", text)
    s = s.translate(_TRANSLATE)
    s = _ZERO_WIDTH.sub("", s)
    s = "".join(ch for ch in s if ch.isspace() or unicodedata.category(ch)[0] != "C")
    return _WS.sub(" ", s).strip()


def words(text: str) -> list[str]:
    """Normalise ``text`` and split it into whitespace-separated words."""
    n = normalize_text(text)
    return n.split(" ") if n else []


def has_digit(token: str) -> bool:
    """True when a token contains a digit (counted as a number for silent-error scoring)."""
    return any(ch.isdigit() for ch in token)
