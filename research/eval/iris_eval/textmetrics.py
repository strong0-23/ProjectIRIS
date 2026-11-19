"""Text and reading-order metrics.

**Text (CER, WER) is order-independent at line level.** Ground-truth lines are normalised
(``iris-norm/1``) and joined with single spaces. Each predicted line is anchored at the position
in that ground-truth text where it matches best (rapidfuzz partial-ratio alignment); predicted
lines are re-sorted by anchor (lines matching nothing, score < 50, go last in their own order),
joined with single spaces, and compared with the ground truth by Levenshtein distance. Anchoring
is a heuristic that can misplace garbled lines, so the reader's own order is used instead whenever
it gives fewer character edits (text scores never exceed the reading-order CER):

- CER = character edits / ground-truth characters;
- WER = word edits / ground-truth words (same re-sorted text, split on spaces).

Re-sorting stops a reader being charged twice (once as text, once as order) for reading
columns in a different order; line breaks never cost more than a space.

**Reading order** is scored only where the ground truth has one (``text.reading_order``):

- ``cer_ordered``: CER of the predicted text in the reader's own order;
- ``order_score``: Kendall-style agreement of the anchors of matched predicted lines (score >= 60,
  at least 3 characters) taken in the reader's order: concordant pairs / comparable pairs.
  1.0 is perfect order; ``None`` when fewer than two lines are comparable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from .docmodel import PredLine, PredWord
from .normalize import normalize_text

MATCH_MIN_SCORE = 50.0
ORDER_MIN_SCORE = 60.0
ORDER_MIN_CHARS = 3


@dataclass
class TextScore:
    gt_chars: int
    char_edits: int
    gt_words: int
    word_edits: int
    ordered_char_edits: int | None
    order_concordant: int | None
    order_pairs: int | None
    gt_word_seq: list[str]
    pred_word_seq: list[PredWord]

    @property
    def cer(self) -> float | None:
        return self.char_edits / self.gt_chars if self.gt_chars else None

    @property
    def wer(self) -> float | None:
        return self.word_edits / self.gt_words if self.gt_words else None

    @property
    def cer_ordered(self) -> float | None:
        if self.ordered_char_edits is None or not self.gt_chars:
            return None
        return self.ordered_char_edits / self.gt_chars

    @property
    def order_score(self) -> float | None:
        if not self.order_pairs or self.order_concordant is None:
            return None
        return self.order_concordant / self.order_pairs


def _anchor(line: str, gt_full: str) -> tuple[float, float]:
    """Position of ``line`` in ``gt_full`` (inf when it matches nothing) and the match score."""
    if not gt_full or not line:
        return math.inf, 0.0
    al = fuzz.partial_ratio_alignment(line, gt_full)
    if al is None or al.score < MATCH_MIN_SCORE:
        return math.inf, al.score if al is not None else 0.0
    return float(al.dest_start), float(al.score)


def score_text(gt_lines: list[str], pred_lines: list[PredLine], reading_order: bool) -> TextScore:
    gt_norm = [n for n in (normalize_text(x) for x in gt_lines) if n]
    gt_full = " ".join(gt_norm)
    preds = [(normalize_text(p.text), p) for p in pred_lines]
    preds = [(t, p) for t, p in preds if t]

    anchors = [_anchor(t, gt_full) for t, _ in preds]
    order = sorted(range(len(preds)), key=lambda i: (anchors[i][0], i))
    pred_sorted = " ".join(preds[i][0] for i in order)

    own_edits = Levenshtein.distance(gt_full, " ".join(t for t, _ in preds))
    sorted_edits = Levenshtein.distance(gt_full, pred_sorted)
    if own_edits <= sorted_edits:
        order = list(range(len(preds)))
    char_edits = min(own_edits, sorted_edits)

    gt_words = gt_full.split(" ") if gt_full else []
    pred_words: list[PredWord] = [w for i in order for w in preds[i][1].words]
    word_edits = Levenshtein.distance(gt_words, [w.text for w in pred_words])

    ordered_edits: int | None = None
    concordant: int | None = None
    pairs: int | None = None
    if reading_order:
        ordered_edits = own_edits
        seq = [
            anchors[i][0]
            for i, (t, _) in enumerate(preds)
            if anchors[i][1] >= ORDER_MIN_SCORE and len(t) >= ORDER_MIN_CHARS and math.isfinite(anchors[i][0])
        ]
        concordant = 0
        pairs = 0
        for a in range(len(seq)):
            for b in range(a + 1, len(seq)):
                if seq[a] == seq[b]:
                    continue
                pairs += 1
                if seq[a] < seq[b]:
                    concordant += 1

    return TextScore(
        gt_chars=len(gt_full),
        char_edits=char_edits,
        gt_words=len(gt_words),
        word_edits=word_edits,
        ordered_char_edits=ordered_edits,
        order_concordant=concordant,
        order_pairs=pairs,
        gt_word_seq=gt_words,
        pred_word_seq=pred_words,
    )
