"""Score a reader's predictions against ground truth, per page, per category and per split.

Predictions are one IRIS document JSON per page at ``<predictions>/<dataset>/<key>.json``
(``run_reader`` writes them; a reader run elsewhere, e.g. on a GPU machine, can write the same
layout). A page with no prediction is scored as an empty output and counted in
``missing_predictions``: nothing is skipped silently.

Outputs (``--out``): ``results.json`` (schema ``iris-results/1``: run info, per-page metrics,
aggregates) and ``summary.md``. Neither ever contains document text, only IDs and numbers.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .docmodel import Cost, PredPage, parse_document
from .gt import PageGT, load_gt, parse_gt
from .index import IndexEntry, load_index
from .kv import score_pairs
from .normalize import NORMALISATION_VERSION
from .private import load_private, read_private_gt
from .silent import cell_silent_errors, word_silent_errors
from .teds import match_tables
from .textmetrics import score_text

RESULTS_SCHEMA = "iris-results/1"
DEFAULT_THRESHOLD = 0.5
HELDOUT_FLAG = "--heldout-scoring-run"


def _empty_pred() -> PredPage:
    return PredPage(lines=[], tables=[], pairs=[], cost=Cost())


def score_page(gt: PageGT, pred: PredPage | None, threshold: float) -> dict[str, Any]:
    missing = pred is None
    p = pred if pred is not None else _empty_pred()
    rec: dict[str, Any] = {
        "id": gt.id,
        "dataset": gt.dataset,
        "category": gt.category,
        "split": gt.split,
        "conditions": gt.conditions,
        "missing_prediction": missing,
        "text": None,
        "order": None,
        "tables": None,
        "kv": None,
        "silent": {"words": None, "cells": None},
        "cost": {
            "seconds": p.cost.seconds,
            "peak_memory_bytes": p.cost.peak_memory_bytes,
            "models": p.cost.models,
        },
    }
    if gt.lines is not None:
        ts = score_text(gt.lines, p.lines, gt.reading_order)
        rec["text"] = {
            "gt_chars": ts.gt_chars,
            "char_edits": ts.char_edits,
            "cer": ts.cer,
            "gt_words": ts.gt_words,
            "word_edits": ts.word_edits,
            "wer": ts.wer,
        }
        if gt.reading_order:
            rec["order"] = {
                "ordered_char_edits": ts.ordered_char_edits,
                "cer_ordered": ts.cer_ordered,
                "order_score": ts.order_score,
                "order_pairs": ts.order_pairs,
            }
        rec["silent"]["words"] = asdict(word_silent_errors(ts.gt_word_seq, ts.pred_word_seq, threshold))
    if gt.tables is not None:
        m = match_tables(gt.tables, p.tables)
        rec["tables"] = {
            "gt_tables": len(gt.tables),
            "pred_tables": len(p.tables),
            "teds": m.score,
            "teds_struct": m.score_struct,
        }
        rec["silent"]["cells"] = asdict(cell_silent_errors(gt.tables, p.tables, m.pairs, threshold))
    if gt.pairs is not None:
        k = score_pairs(gt.pairs, p.pairs, threshold)
        rec["kv"] = {**asdict(k), "accuracy": k.accuracy, "precision": k.precision}
    return rec


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def _mean(xs: Iterable[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return statistics.fmean(vals) if vals else None


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, round(q * (len(s) - 1))))
    return s[k]


def aggregate(pages: list[dict[str, Any]]) -> dict[str, Any]:
    text = [p["text"] for p in pages if p["text"]]
    order = [p["order"] for p in pages if p["order"]]
    tables = [p["tables"] for p in pages if p["tables"]]
    kv = [p["kv"] for p in pages if p["kv"]]
    sw = [p["silent"]["words"] for p in pages if p["silent"]["words"]]
    sc = [p["silent"]["cells"] for p in pages if p["silent"]["cells"]]
    secs = [p["cost"]["seconds"] for p in pages if p["cost"]["seconds"] is not None]
    mems = [p["cost"]["peak_memory_bytes"] for p in pages if p["cost"]["peak_memory_bytes"] is not None]
    models: dict[str, int | None] = {}
    for p in pages:
        models.update(p["cost"]["models"])
    sizes = [v for v in models.values() if v is not None]

    def s(rows: list[dict[str, Any]], k: str) -> float:
        return float(sum(r[k] for r in rows))

    wrong_w = s(sw, "wrong_words")
    return {
        "pages": len(pages),
        "missing_predictions": sum(1 for p in pages if p["missing_prediction"]),
        "text_pages": len(text),
        "cer": _ratio(s(text, "char_edits"), s(text, "gt_chars")),
        "wer": _ratio(s(text, "word_edits"), s(text, "gt_words")),
        "order_pages": len(order),
        "cer_ordered": _ratio(float(sum(o["ordered_char_edits"] for o in order)),
                              float(sum(p["text"]["gt_chars"] for p in pages if p["order"]))),
        "order_score": _mean(o["order_score"] for o in order),
        "table_pages": len(tables),
        "teds": _mean(t["teds"] for t in tables),
        "teds_struct": _mean(t["teds_struct"] for t in tables),
        "kv_pages": len(kv),
        "kv_accuracy": _ratio(s(kv, "correct"), s(kv, "gt_pairs")),
        "kv_precision": _ratio(s(kv, "correct"), s(kv, "pred_pairs")),
        "kv_silent_wrong_values": int(s(kv, "silent_wrong_values")),
        "silent_word_rate": _ratio(s(sw, "silent_words"), s(sw, "gt_words")),
        "wrong_word_rate": _ratio(wrong_w, s(sw, "gt_words")),
        "flag_recall": _ratio(wrong_w - s(sw, "silent_words"), wrong_w),
        "false_flag_rate": _ratio(s(sw, "false_flags"), s(sw, "pred_words") - wrong_w),
        "missed_word_rate": _ratio(s(sw, "missed_words"), s(sw, "gt_words")),
        "silent_number_rate": _ratio(s(sw, "silent_numbers"), s(sw, "gt_numbers")),
        "silent_cell_rate": _ratio(s(sc, "silent_cells"), s(sc, "gt_cells")),
        "seconds_per_page_mean": _mean(secs),
        "seconds_per_page_p50": _pct(secs, 0.5),
        "seconds_per_page_p95": _pct(secs, 0.95),
        "peak_memory_bytes_max": max(mems) if mems else None,
        "model_download_bytes": sum(sizes) if sizes else None,
        "models": sorted(models),
    }


def aggregate_all(pages: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in pages:
        groups.setdefault(f"{p['split']}|{p['category']}", []).append(p)
        groups.setdefault(f"{p['split']}|{p['category']}|{p['dataset']}", []).append(p)
        groups.setdefault(f"{p['split']}|ALL", []).append(p)
    return {k: aggregate(v) for k, v in sorted(groups.items())}


def _fmt(v: Any, pct: bool = False, scale: float = 1.0, digits: int = 3) -> str:
    if v is None:
        return "-"
    if pct:
        return f"{100 * v:.1f}%"
    return f"{v / scale:.{digits}f}"


COLUMNS: list[tuple[str, Callable[[dict[str, Any]], str]]] = [
    ("Pages", lambda a: str(a["pages"])),
    ("Missing", lambda a: str(a["missing_predictions"])),
    ("CER", lambda a: _fmt(a["cer"], pct=True)),
    ("WER", lambda a: _fmt(a["wer"], pct=True)),
    ("CER in reader order", lambda a: _fmt(a["cer_ordered"], pct=True)),
    ("Order score", lambda a: _fmt(a["order_score"])),
    ("TEDS", lambda a: _fmt(a["teds"])),
    ("TEDS-struct", lambda a: _fmt(a["teds_struct"])),
    ("KV accuracy", lambda a: _fmt(a["kv_accuracy"], pct=True)),
    ("Silent words", lambda a: _fmt(a["silent_word_rate"], pct=True)),
    ("Silent numbers", lambda a: _fmt(a["silent_number_rate"], pct=True)),
    ("Silent cells", lambda a: _fmt(a["silent_cell_rate"], pct=True)),
    ("Missed words", lambda a: _fmt(a["missed_word_rate"], pct=True)),
    ("Flag recall", lambda a: _fmt(a["flag_recall"], pct=True)),
    ("s/page mean", lambda a: _fmt(a["seconds_per_page_mean"], digits=2)),
    ("s/page p95", lambda a: _fmt(a["seconds_per_page_p95"], digits=2)),
    ("Peak MB", lambda a: _fmt(a["peak_memory_bytes_max"], scale=1e6, digits=0)),
    ("Model MB", lambda a: _fmt(a["model_download_bytes"], scale=1e6, digits=1)),
]


def summary_markdown(run: dict[str, Any], aggregates: dict[str, Any]) -> str:
    out = [
        f"# Evaluation summary: {run['reader']}",
        "",
        f"- Created: {run['created']}",
        f"- Splits: {', '.join(run['splits'])}; datasets: {', '.join(run['datasets']) or '-'}",
        f"- Confidence threshold: {run['confidence_threshold']}; normalisation: {run['normalisation']}",
        "- CER/WER: order-independent at line level; '-' means not annotated or not applicable.",
        "",
    ]
    header = "| Split | Category | Dataset | " + " | ".join(c for c, _ in COLUMNS) + " |"
    sep = "|" + "---|" * (3 + len(COLUMNS))
    out += [header, sep]
    for key, agg in aggregates.items():
        parts = key.split("|")
        split, cat = parts[0], parts[1]
        ds = parts[2] if len(parts) > 2 else ("all" if cat != "ALL" else "")
        row = [split, "**all**" if cat == "ALL" else cat, ds] + [f(agg) for _, f in COLUMNS]
        out.append("| " + " | ".join(row) + " |")
    out.append("")
    return "\n".join(out)


def _gt_for(entry: IndexEntry) -> PageGT:
    if entry.private:
        return parse_gt(read_private_gt(entry))
    return load_gt(entry.gt_path)


def collect_entries(datasets: list[str], private: bool, split: str) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    for d in datasets:
        entries += [e for e in load_index(d) if e.split == split]
    if private:
        entries += load_private(split)
    return entries


def run_scoring(
    entries: list[IndexEntry], predictions: Path, threshold: float | None
) -> tuple[list[dict[str, Any]], float]:
    preds: dict[str, PredPage | None] = {}
    for e in entries:
        f = predictions / e.dataset / f"{e.key}.json"
        if f.is_file():
            with f.open(encoding="utf-8") as fh:
                preds[e.id] = parse_document(json.load(fh))
        else:
            preds[e.id] = None
    if threshold is None:
        declared = [p.declared_threshold for p in preds.values() if p and p.declared_threshold is not None]
        threshold = declared[0] if declared else DEFAULT_THRESHOLD
    pages = [score_page(_gt_for(e), preds[e.id], threshold) for e in entries]
    return pages, threshold


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--dataset", action="append", default=[], help="prepared dataset id (repeatable)")
    ap.add_argument("--private", action="store_true", help="also score $OCR_PRIVATE_DATA")
    ap.add_argument("--split", choices=["dev", "heldout"], default="dev")
    ap.add_argument(HELDOUT_FLAG, action="store_true", dest="heldout_ok",
                    help="required to score held-out pages (reporting runs only)")
    ap.add_argument("--conf-threshold", type=float, default=None)
    ap.add_argument("--reader-name", default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.split == "heldout" and not a.heldout_ok:
        print(f"refusing to score held-out without {HELDOUT_FLAG} (E2: held-out is for reporting only)",
              file=sys.stderr)
        return 2
    entries = collect_entries(a.dataset, a.private, a.split)
    if not entries:
        print("no pages to score (prepare a dataset or set OCR_PRIVATE_DATA)", file=sys.stderr)
        return 1
    pages, thr = run_scoring(entries, a.predictions, a.conf_threshold)
    run = {
        "reader": a.reader_name or a.predictions.name,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "harness_version": __version__,
        "normalisation": NORMALISATION_VERSION,
        "confidence_threshold": thr,
        "splits": [a.split],
        "datasets": a.dataset + (["private"] if a.private else []),
    }
    aggs = aggregate_all(pages)
    a.out.mkdir(parents=True, exist_ok=True)
    with (a.out / "results.json").open("w", encoding="utf-8") as f:
        json.dump({"schema": RESULTS_SCHEMA, "run": run, "aggregates": aggs, "pages": pages}, f, indent=1)
    (a.out / "summary.md").write_text(summary_markdown(run, aggs), encoding="utf-8")
    print(f"scored {len(pages)} pages -> {a.out / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
