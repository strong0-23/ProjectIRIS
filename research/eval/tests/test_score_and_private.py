import json
from pathlib import Path

import pytest
from PIL import Image

from conftest import doc, para, word
from iris_eval import score
from iris_eval.gt import PageGT
from iris_eval.private import PrivateDataError, load_private

SECRET = "Zyxwvut Secretname"


def _write_private(root: Path) -> None:
    d = root / "receipts"
    d.mkdir(parents=True)
    Image.new("RGB", (20, 20), "white").save(d / "r1.png")
    (d / "r1.gt.json").write_text(json.dumps({
        "text": {"lines": [SECRET, "Total 12.50"], "reading_order": True},
        "pairs": [{"key": "Total", "field": "total", "value": "12.50"}],
        "tables": None,
    }))


def test_private_slot_scores_by_id_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "private"
    _write_private(root)
    seen = tmp_path / "seen.txt"
    seen.write_text("receipts/r1.png\n")  # seen photos are always dev (O7)
    monkeypatch.setenv("OCR_PRIVATE_DATA", str(root))
    monkeypatch.setenv("OCR_PRIVATE_SEEN", str(seen))
    entries = load_private("dev")
    assert [e.id for e in entries] == ["private/receipts/r1"]
    preds = tmp_path / "preds" / "private"
    preds.mkdir(parents=True)
    # The key-value block has no lines, so it contributes the text "Total 12.80" itself.
    d = doc(para([word("Zyxwvut"), word("Secretname")]),
            {"type": "keyValue", "pairs": [{"key": "Total", "value": "12.80", "field": "total", "confidence": 0.9}]})
    (preds / f"{entries[0].key}.json").write_text(json.dumps(d))
    out = tmp_path / "out"
    assert score.main(["--predictions", str(tmp_path / "preds"), "--private", "--split", "dev",
                       "--out", str(out)]) == 0
    results = (out / "results.json").read_text()
    summary = (out / "summary.md").read_text()
    for text in ("Zyxwvut", "Secretname", "12.50", "12.80"):
        assert text not in results and text not in summary
    r = json.loads(results)
    page = r["pages"][0]
    assert page["id"] == "private/receipts/r1"
    assert page["kv"]["correct"] == 0 and page["kv"]["silent_wrong_values"] == 1
    assert page["silent"]["words"]["silent_numbers"] == 1


def test_old_private_layout_is_an_error(tmp_path: Path) -> None:
    d = tmp_path / "dev" / "forms"
    d.mkdir(parents=True)
    (d / "f1.gt.json").write_text("{}")
    with pytest.raises(PrivateDataError, match="old dev/ and heldout/ layout"):
        load_private("dev", tmp_path)


def test_no_private_env_means_no_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCR_PRIVATE_DATA", raising=False)
    assert load_private("dev") == []


def test_heldout_needs_explicit_flag(tmp_path: Path) -> None:
    assert score.main(["--predictions", str(tmp_path), "--split", "heldout", "--out", str(tmp_path / "o")]) == 2


def test_missing_prediction_is_scored_not_skipped() -> None:
    gt = PageGT("d/p", "d", "letters-and-reports", "dev", "x.png", lines=["hello world"], reading_order=True)
    rec = score.score_page(gt, None, 0.5)
    assert rec["missing_prediction"] is True
    assert rec["text"]["cer"] == 1.0


def test_aggregate_micro_and_cost() -> None:
    gt1 = PageGT("d/a", "d", "forms", "dev", "a.png", lines=["abcd"])
    gt2 = PageGT("d/b", "d", "forms", "dev", "b.png", lines=["abcdefgh"])
    from iris_eval.docmodel import parse_document
    p1 = parse_document(doc(para("abcx"), source={"timings": {"totalSeconds": 1.0}, "peakMemoryBytes": 10,
                                                  "models": [{"name": "m", "sizeBytes": 5}]}))
    p2 = parse_document(doc(para("abcdefgh"), source={"timings": {"totalSeconds": 3.0}, "peakMemoryBytes": 30,
                                                      "models": [{"name": "m", "sizeBytes": 5}]}))
    aggs = score.aggregate_all([score.score_page(gt1, p1, 0.5), score.score_page(gt2, p2, 0.5)])
    a = aggs["dev|forms"]
    assert a["cer"] == pytest.approx(1 / 12)
    assert a["seconds_per_page_mean"] == 2.0
    assert a["peak_memory_bytes_max"] == 30
    assert a["model_download_bytes"] == 5
    assert "dev|forms|d" in aggs and "dev|ALL" in aggs
    assert "| dev | forms |" in score.summary_markdown(
        {"reader": "r", "created": "t", "splits": ["dev"], "datasets": ["d"],
         "confidence_threshold": 0.5, "normalisation": "n"}, aggs)
