# Evaluation data

Manifests and scripts for the evaluation set (docs/DECISIONS.md E2). **No dataset files are
committed here.** Downloads and everything derived from them live in `eval/.data/` (git-ignored).
The scoring harness is in `research/eval/`.

```
eval/
  manifests/<dataset>.json   one per dataset: source, licence, categories, ground truth, files + checksums, split rule
  splits/<dataset>.json      frozen dev / held-out page IDs per category (IDs only), with sha256 digests
  download.py                fetch, checksum and unpack (Python standard library only)
  .data/                     git-ignored: raw/, gt/, index/, runs/
```

## Quick start

```bash
pip install -r research/eval/requirements.txt          # plus Tesseract 5 with eng for the baseline
python eval/download.py --list
python eval/download.py pubtabnet-final-eval
export PYTHONPATH=research/eval
python -m iris_eval.prepare pubtabnet-final-eval        # applies the split, checks eval/splits/
python -m iris_eval.run_reader --reader tesseract --dataset pubtabnet-final-eval \
    --split dev --out eval/.data/runs/tesseract-dev/predictions
python -m iris_eval.score --predictions eval/.data/runs/tesseract-dev/predictions \
    --dataset pubtabnet-final-eval --split dev --out eval/.data/runs/tesseract-dev
```

`score` writes `results.json` (schema `iris-results/1`) and `summary.md`. Add `--private` to
`run_reader` and `score` to include the private slot.

## Categories

`receipts`, `invoices`, `forms`, `letters-and-reports`, `tables`, `book-or-scanned-pages`,
`screenshots`, `phone-photos-hard` (crumpled, torn, faded, low light, skewed, shadowed). A page
belongs to one category; capture conditions go in the GT's `conditions` list.

## Licence gate (O4)

Each manifest has a `use`:

| use | meaning | download.py |
|---|---|---|
| `allowed` | licence allows commercial use and redistribution | downloads |
| `evaluation-only-needs-decision` | non-commercial or no-redistribution licence; can never ship | needs an owner decision, then `--accept-eval-only` |
| `excluded` | licence missing or unclear | refuses |

Files without a pinned checksum need `--allow-unpinned` once; the script prints the sha256 to pin.

## Datasets (manifests as of 19 Nov 2026)

| id | categories | licence | use | here |
|---|---|---|---|---|
| pubtabnet-final-eval | tables | CDLA-Permissive-1.0 (annotations); PMC OA commercial-use terms (images) | allowed | downloaded |
| cord-v2 | receipts | CC BY 4.0 | allowed | host not reachable |
| doclaynet | letters-and-reports | CDLA-Permissive-1.0 | allowed | host not reachable |
| fatura | invoices (synthetic) | CC BY 4.0 | allowed | host not reachable |
| smartdoc2015-ch2 | phone-photos-hard | CC BY 4.0 | allowed | host not reachable |
| tabrecset | tables, phone-photos-hard | CC BY-SA 4.0 | allowed | host not reachable |
| olmocr-bench | book-or-scanned-pages, letters-and-reports, tables | ODC-BY-1.0 | allowed (unit-test GT, metric not built yet) | host not reachable |
| funsd | forms | non-commercial research | evaluation-only-needs-decision | host not reachable |
| omnidocbench | book-or-scanned-pages, letters-and-reports, tables, screenshots | research only, non-commercial | evaluation-only-needs-decision | host not reachable |
| bln600 | book-or-scanned-pages | CC BY-NC-ND 4.0 | evaluation-only-needs-decision | host not reachable |
| sroie | receipts | none stated | excluded | - |
| vrdu | forms | none stated | excluded | - |
| ctdar2019 | tables | none stated | excluded | - |
| uvdoc | phone-photos-hard | none stated | excluded | - |

Only `pubtabnet-final-eval` has a converter so far; a converter for each other dataset is written
once its files can be fetched and its format checked (`iris_eval/datasets/`).

## Splits: `iris-split/1`

Per (dataset, category): drop `split.exclude`; rank page IDs by
`sha256("<seed>:<dataset>:<page id>")`; keep the first `sample_per_category`; the first
`round(n * dev_fraction)` are **dev**, the rest **held-out**. Seed `iris-wo001`, dev fraction 0.6.
Sample sizes: 100 for PubTabNet (60 / 40), 75 elsewhere (45 / 30), so each category reaches at
least 30 held-out pages where the data allows. The split depends only on IDs, never on content.

`prepare` recomputes the split and fails if it differs from `eval/splits/<dataset>.json`
(`--write-splits` writes it the first time only). Changing a frozen split is an orchestrator
decision.

**Held-out pages are never read by agents** (AGENTS.md). `run_reader` and `score` refuse
`--split heldout` without `--heldout-scoring-run`, which is for reporting runs only. Every tool
prints counts, never document content, and results never contain text.

## Private slot: `OCR_PRIVATE_DATA`

Your own documents stay outside the repository:

```
$OCR_PRIVATE_DATA/
  dev/<category>/<page id>.png|jpg|jpeg|tif|tiff|webp
  dev/<category>/<page id>.gt.json
  heldout/<category>/...
```

You choose the split by folder. Each `.gt.json` follows the GT format below; `id`, `dataset`,
`category`, `split` and `image` can be omitted (taken from the path). Private pages are scored
like public ones and reported by ID only. Keep run outputs under `eval/.data/` (the default),
which git ignores.

## Ground-truth format: `iris-gt/1`

```json
{
  "schema": "iris-gt/1",
  "id": "<dataset>/<native id>", "dataset": "...", "category": "receipts", "split": "dev",
  "image": "<path>",
  "conditions": ["crumpled", "low-light"],
  "text":   {"lines": ["SHOP NAME", "Total 12.50"], "reading_order": true},
  "tables": [{"cells": [{"row": 0, "col": 0, "rowSpan": 1, "colSpan": 1, "text": "Item"}]}],
  "pairs":  [{"key": "Total", "field": "total", "value": "12.50"}]
}
```

`null` (or absent) = not annotated, so that metric is skipped; `[]` = annotated, none present.
`lines` are in reading order when `reading_order` is true. Keep line order natural; line breaks
do not cost anything in CER.

## Metrics

Defined in `research/eval/iris_eval/` (each module's docstring) and recorded in
docs/DECISIONS.md E7: CER and WER (order-independent at line level, `iris-norm/1`
normalisation), reading order (CER in the reader's order plus a pairwise order score), TEDS and
TEDS-struct, key-value accuracy, silent errors (words, numbers, cells, key-values; visible =
flagged or confidence below the threshold, default 0.5), missed words, flag recall, false flags,
and cost (seconds per page, peak memory, model download size).
