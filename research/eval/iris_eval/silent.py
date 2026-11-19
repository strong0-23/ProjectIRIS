"""Silent errors (docs/DECISIONS.md E3): output that is wrong and not marked as doubtful.

An output element is *visible* when it is flagged (its own, its line's or its block's ``flags``)
or its confidence is below the threshold; otherwise it is presented as fact. A wrong element
that is not visible is a **silent error**.

Words. The predicted words (in the order produced by ``textmetrics``) are aligned to the
ground-truth words by word-level Levenshtein edit operations:

- a predicted word that replaces a ground-truth word, or is inserted, is *wrong*;
- a ground-truth word that is deleted is *missed*: an omission no flag can be attached to,
  reported separately as ``missed_words``;
- a correct word that is visible is a *false flag* (a doubt that cost the user a glance for
  nothing).

Numbers. The same alignment restricted to tokens with a digit: a replace where either side has a
digit, or an inserted token with a digit. The denominator is ground-truth tokens with a digit.

Cells. For each matched table pair, predicted cells are compared with the ground-truth cell at the
same (row, col) anchor; a predicted cell is wrong when its normalised text differs or no
ground-truth cell is anchored there. Cells of unmatched predicted tables that hold text are wrong.
Denominator: ground-truth cells.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from .docmodel import PredWord
from .gt import Table
from .kv import visible
from .normalize import has_digit, normalize_text


@dataclass
class WordSilent:
    gt_words: int
    pred_words: int
    wrong_words: int
    silent_words: int
    missed_words: int
    false_flags: int
    gt_numbers: int
    wrong_numbers: int
    silent_numbers: int


def word_silent_errors(gt_words: list[str], pred_words: list[PredWord], threshold: float) -> WordSilent:
    ops = Levenshtein.editops(gt_words, [w.text for w in pred_words])
    wrong_pred: set[int] = set()
    missed = 0
    wrong_num: set[int] = set()
    for op in ops:
        if op.tag == "replace":
            wrong_pred.add(op.dest_pos)
            if has_digit(gt_words[op.src_pos]) or has_digit(pred_words[op.dest_pos].text):
                wrong_num.add(op.dest_pos)
        elif op.tag == "insert":
            wrong_pred.add(op.dest_pos)
            if has_digit(pred_words[op.dest_pos].text):
                wrong_num.add(op.dest_pos)
        elif op.tag == "delete":
            missed += 1
    silent = 0
    false_flags = 0
    for i, w in enumerate(pred_words):
        vis = visible(w.confidence, w.flagged, threshold)
        if i in wrong_pred and not vis:
            silent += 1
        elif i not in wrong_pred and vis:
            false_flags += 1
    silent_num = sum(
        1 for i in wrong_num if not visible(pred_words[i].confidence, pred_words[i].flagged, threshold)
    )
    return WordSilent(
        gt_words=len(gt_words),
        pred_words=len(pred_words),
        wrong_words=len(wrong_pred),
        silent_words=silent,
        missed_words=missed,
        false_flags=false_flags,
        gt_numbers=sum(1 for w in gt_words if has_digit(w)),
        wrong_numbers=len(wrong_num),
        silent_numbers=silent_num,
    )


@dataclass
class CellSilent:
    gt_cells: int
    pred_cells: int
    wrong_cells: int
    silent_cells: int


def cell_silent_errors(
    gt: Sequence[Table], pred: Sequence[Table], pairs: list[tuple[int, int]], threshold: float
) -> CellSilent:
    wrong = 0
    silent = 0
    matched_pred = {j for _, j in pairs}
    for i, j in pairs:
        gmap = {(c.row, c.col): normalize_text(c.text) for c in gt[i].cells}
        for c in pred[j].cells:
            if gmap.get((c.row, c.col)) != normalize_text(c.text):
                wrong += 1
                if not visible(c.confidence, c.flagged, threshold):
                    silent += 1
    for j, t in enumerate(pred):
        if j in matched_pred:
            continue
        for c in t.cells:
            if normalize_text(c.text):
                wrong += 1
                if not visible(c.confidence, c.flagged, threshold):
                    silent += 1
    return CellSilent(
        gt_cells=sum(len(t.cells) for t in gt),
        pred_cells=sum(len(t.cells) for t in pred),
        wrong_cells=wrong,
        silent_cells=silent,
    )
