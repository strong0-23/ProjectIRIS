"""The private slot (O7): rule-based frozen split, seen list, ground truth and the SplitLah converter.
Synthetic files only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from iris_eval import private as pv
from iris_eval.private import (
    ASSIGN_FILE,
    PrivateDataError,
    load_private,
    load_seen,
    money,
    read_private_gt,
    rule_split,
    splitlah_to_gt,
    status,
    sync_assignments,
)


def _photo(root: Path, rel: str, colour: tuple[int, int, int]) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), colour).save(p)
    return p


def _many(root: Path, n: int, cat: str = "receipts") -> list[Path]:
    return [_photo(root, f"{cat}/IMG_{i:03d}.png", (i % 256, i // 256, 7)) for i in range(n)]


def test_rule_is_deterministic_and_near_the_dev_fraction() -> None:
    import hashlib

    hashes = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(2000)]
    splits = [rule_split(h) for h in hashes]
    assert splits == [rule_split(h) for h in hashes]
    assert 0.55 < splits.count("dev") / len(splits) < 0.65


def test_first_sight_assigns_and_freezes(tmp_path: Path) -> None:
    root = tmp_path / "priv"
    _many(root, 30)
    rec = sync_assignments(root, today="2026-11-23")
    assert len(rec["photos"]) == 30 and (root / ASSIGN_FILE).is_file()
    assert {v["reason"] for v in rec["photos"].values()} == {"rule"}
    before = {k: v["split"] for k, v in rec["photos"].items()}
    # Even if the rule's parameter changes later, frozen photos keep their split.
    d = json.loads((root / ASSIGN_FILE).read_text())
    d["dev_fraction"] = 0.01
    (root / ASSIGN_FILE).write_text(json.dumps(d))
    rec2 = sync_assignments(root)
    assert {k: v["split"] for k, v in rec2["photos"].items()} == before
    # A new photo is assigned once, with the stored parameter.
    _photo(root, "receipts/NEW.png", (1, 2, 3))
    rec3 = sync_assignments(root, today="2026-12-01")
    assert rec3["photos"]["receipts/NEW.png"]["first_seen"] == "2026-12-01"


def test_seen_list_forces_dev_and_moves_seen_heldout(tmp_path: Path) -> None:
    root = tmp_path / "priv"
    photos = _many(root, 20)
    rec = sync_assignments(root)
    held = sorted(k for k, v in rec["photos"].items() if v["split"] == "heldout")
    assert held
    seen_file = tmp_path / "seen.txt"
    target_sha = rec["photos"][held[1]]["sha256"]
    seen_file.write_text(f"# photos agents saw\n{held[0].split('/')[1]}\n{target_sha.upper()}\n")
    rec2 = sync_assignments(root, load_seen(seen_file))
    for k in held[:2]:
        assert rec2["photos"][k]["split"] == "dev" and rec2["photos"][k]["reason"] == "seen-after-assignment"
    new = _photo(root, "receipts/seen_new.png", (9, 9, 9))
    seen_file.write_text("receipts/seen_new.png\n")
    rec3 = sync_assignments(root, load_seen(seen_file))
    assert rec3["photos"]["receipts/seen_new.png"]["reason"] == "seen"
    assert new.is_file() and len(photos) == 20


def test_renamed_photo_keeps_its_split(tmp_path: Path) -> None:
    root = tmp_path / "priv"
    p = _photo(root, "invoices/a.png", (5, 5, 5))
    s1 = sync_assignments(root)["photos"]["invoices/a.png"]["split"]
    p.rename(root / "invoices" / "renamed.png")
    assert sync_assignments(root)["photos"]["invoices/renamed.png"]["split"] == s1


def test_unknown_folders_are_skipped_and_counts_have_no_names(tmp_path: Path) -> None:
    root = tmp_path / "priv"
    _many(root, 5, "receipts")
    _photo(root, "holiday-snaps/x.png", (1, 1, 1))
    (root / "receipts" / "IMG_000.gt.json").write_text(json.dumps({"pairs": []}))
    st = status(root)
    assert st["skipped_folders"] == 1
    c = st["categories"]["receipts"]
    assert c["dev"] + c["heldout"] == 5 and c["with_gt"] == 1
    assert "IMG_" not in json.dumps(st)


def test_load_private_needs_ground_truth_and_reads_splitlah(tmp_path: Path) -> None:
    root = tmp_path / "priv"
    photos = _many(root, 12)
    rec = sync_assignments(root)
    for p in photos:
        ref = {"merchant": "Synthetic Kopitiam", "currency": "SGD",
               "items": [{"name": "Kopi", "quantity": 2, "amount": 360}], "charges": {"gst": 32}, "total": 392}
        (p.parent / (p.name + ".gt.json")).write_text(json.dumps(ref))  # <file name>.gt.json also accepted
    dev = load_private("dev", root, pv.SeenList.empty())
    held = load_private("heldout", root, pv.SeenList.empty())
    assert len(dev) + len(held) == 12
    want = {k.split("/")[1][:-4] for k, v in rec["photos"].items() if v["split"] == "dev"}
    assert {e.id.split("/")[-1] for e in dev} == want
    gt = read_private_gt(dev[0])
    assert gt["split"] == "dev" and gt["text"] is None
    assert {"key": "Kopi", "field": "item_amount", "value": "3.60"} in gt["pairs"]  # type: ignore[operator]


def test_splitlah_converter_full_and_tolerant() -> None:
    full = {"schema": "splitlah-ref/1", "merchant": {"name": "Synthetic Cafe"}, "currency": "SGD",
            "items": [{"name": "Chicken  rice", "quantity": 2, "amount": 900},
                      {"description": "Teh", "qty": "1", "amount_cents": "180"}],
            "charges": [{"type": "Service", "amount": 108}, {"type": "GST", "amount": 107},
                        {"type": "discount", "amount": -100}, {"type": "rounding", "amount": 0}],
            "printed_total": 1195}
    gt = splitlah_to_gt(full)
    fields = [(p["field"], p["key"], p["value"]) for p in gt["pairs"]]
    assert ("merchant", None, "Synthetic Cafe") in fields
    assert ("item_amount", "Chicken rice", "9.00") in fields and ("item_quantity", "Chicken rice", "2") in fields
    assert ("item_amount", "Teh", "1.80") in fields
    assert ("service_charge", None, "1.08") in fields and ("gst", None, "1.07") in fields
    assert ("discount", None, "-1.00") in fields and ("total", None, "11.95") in fields
    assert not any(f == "rounding" for f, _, _ in fields)  # zero charges are not printed
    minimal = splitlah_to_gt({"items": [{"name": "X"}], "total": 5})
    assert [p["field"] for p in minimal["pairs"]] == ["item_name", "total"]
    assert minimal["pairs"][1]["value"] == "0.05"
    with pytest.raises(PrivateDataError):
        splitlah_to_gt({"items": [], "total": None})
    with pytest.raises(PrivateDataError, match="cents"):
        splitlah_to_gt({"items": [{"name": "X", "amount": "9.00"}]})
    assert money(-5) == "-0.05" and money(123456) == "1234.56"


def test_convert_cli(tmp_path: Path) -> None:
    ref = tmp_path / "r.json"
    ref.write_text(json.dumps({"items": [{"name": "A", "amount": 100}], "total": 100}))
    out = tmp_path / "r.gt.json"
    assert pv.main(["convert-splitlah", str(ref), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["schema"] == "iris-gt/1"
