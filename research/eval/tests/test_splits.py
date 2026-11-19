import json
from pathlib import Path

import pytest

from iris_eval.index import SplitMismatch, check_frozen, compute_splits, frozen_record
from iris_eval.paths import SPLITS_DIR
from iris_eval.splits import list_digest, split_ids

IDS = [f"page{i:03d}" for i in range(100)]


def test_deterministic_and_sixty_forty() -> None:
    a = split_ids(IDS, seed="s", dataset="d", dev_fraction=0.6, sample=None)
    b = split_ids(list(reversed(IDS)), seed="s", dataset="d", dev_fraction=0.6, sample=None)
    assert a == b
    assert len(a["dev"]) == 60 and len(a["heldout"]) == 40
    assert not set(a["dev"]) & set(a["heldout"])


def test_seed_sample_and_exclude() -> None:
    a = split_ids(IDS, seed="s", dataset="d", dev_fraction=0.6, sample=50, exclude=["page000", "page001"])
    assert len(a["dev"]) + len(a["heldout"]) == 50
    assert "page000" not in a["dev"] + a["heldout"]
    c = split_ids(IDS, seed="other", dataset="d", dev_fraction=0.6, sample=None)
    assert c != split_ids(IDS, seed="s", dataset="d", dev_fraction=0.6, sample=None)
    with pytest.raises(ValueError):
        split_ids(IDS, seed="s", dataset="d", dev_fraction=1.0, sample=None)


def _manifest() -> dict:
    return {"id": "toy", "split": {"rule": "iris-split/1", "seed": "s", "dev_fraction": 0.6,
                                   "sample_per_category": 10, "exclude": []}}


def test_per_category_and_frozen_check(tmp_path: Path) -> None:
    pages = [(i, "receipts") for i in IDS[:30]] + [(i, "forms") for i in IDS[30:]]
    s = compute_splits(_manifest(), pages)
    assert set(s) == {"forms", "receipts"}
    assert all(len(v["dev"]) == 6 and len(v["heldout"]) == 4 for v in s.values())
    rec = frozen_record(_manifest(), s)
    with pytest.raises(SplitMismatch):
        check_frozen(rec, tmp_path, write=False)
    assert check_frozen(rec, tmp_path, write=True) == "frozen split written"
    assert check_frozen(rec, tmp_path, write=False) == "matches frozen split"
    dropped = s["forms"]["dev"][0]  # a page that was chosen: the data changed
    rec2 = frozen_record(_manifest(), compute_splits(_manifest(), [p for p in pages if p[0] != dropped]))
    with pytest.raises(SplitMismatch):
        check_frozen(rec2, tmp_path, write=False)


def test_committed_frozen_splits_are_consistent() -> None:
    files = sorted(SPLITS_DIR.glob("*.json"))
    assert files, "expected at least one frozen split"
    for f in files:
        rec = json.loads(f.read_text())
        manifest = json.loads((SPLITS_DIR.parent / "manifests" / f.name).read_text())
        excluded = set(manifest["split"]["exclude"])
        assert rec["seed"] == manifest["split"]["seed"]
        for s in rec["categories"].values():
            assert list_digest(s["dev"]) == s["dev_sha256"]
            assert list_digest(s["heldout"]) == s["heldout_sha256"]
            assert not set(s["dev"]) & set(s["heldout"])
            assert not excluded & (set(s["dev"]) | set(s["heldout"]))
            n = len(s["dev"]) + len(s["heldout"])
            assert len(s["dev"]) == round(n * rec["dev_fraction"])
