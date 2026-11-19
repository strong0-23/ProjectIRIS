"""Key-value scoring (field accuracy), where the ground truth has key-values.

A ground-truth pair is *correct* when some unused predicted pair has

- the same value after ``iris-norm/1``, and
- a compatible key: equal ``field`` names when both sides name a field; otherwise key texts with
  a normalised similarity >= 80 (rapidfuzz ratio, trailing ``:`` ignored) when both give a key;
  otherwise any key (value-only match).

``accuracy`` = correct / ground-truth pairs; ``precision`` = correct / predicted pairs.
A predicted pair whose key matches a ground-truth pair but whose value is wrong is a *wrong
value*; it is *silent* when it is neither flagged nor below the confidence threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from .gt import Pair
from .normalize import normalize_text

KEY_MIN_SIMILARITY = 80.0


@dataclass
class KVScore:
    gt_pairs: int
    pred_pairs: int
    correct: int
    wrong_values: int
    silent_wrong_values: int

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.gt_pairs if self.gt_pairs else None

    @property
    def precision(self) -> float | None:
        return self.correct / self.pred_pairs if self.pred_pairs else None


def _key(s: str | None) -> str:
    return normalize_text(s or "").rstrip(":").strip().casefold()


def _key_ok(g: Pair, p: Pair) -> bool:
    if g.field and p.field:
        return g.field == p.field
    if g.key and p.key:
        return fuzz.ratio(_key(g.key), _key(p.key)) >= KEY_MIN_SIMILARITY
    return True


def _key_named(g: Pair, p: Pair) -> bool:
    """True when the two pairs name the same key or field (not a value-only match)."""
    if g.field and p.field:
        return g.field == p.field
    if g.key and p.key:
        return fuzz.ratio(_key(g.key), _key(p.key)) >= KEY_MIN_SIMILARITY
    return False


def visible(confidence: float | None, flagged: bool, threshold: float) -> bool:
    """An output element is visible (not silent) when flagged or below the threshold."""
    return flagged or (confidence is not None and confidence < threshold)


def score_pairs(gt: list[Pair], pred: list[Pair], threshold: float) -> KVScore:
    used: set[int] = set()
    correct = 0
    unmatched_gt: list[Pair] = []
    for g in gt:
        gv = normalize_text(g.value)
        hit = None
        for j, p in enumerate(pred):
            if j not in used and normalize_text(p.value) == gv and _key_ok(g, p):
                hit = j
                break
        if hit is None:
            unmatched_gt.append(g)
        else:
            used.add(hit)
            correct += 1
    wrong = 0
    silent = 0
    for g in unmatched_gt:
        for j, p in enumerate(pred):
            if j not in used and _key_named(g, p):
                used.add(j)
                wrong += 1
                if not visible(p.confidence, p.flagged, threshold):
                    silent += 1
                break
    return KVScore(len(gt), len(pred), correct, wrong, silent)
