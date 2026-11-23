# Evaluation data

Manifests and scripts for the evaluation set (docs/DECISIONS.md E2, O6). **No dataset files are
committed here.** Downloads and everything derived from them live in `eval/.data/` (git-ignored).
The scoring harness is in `research/eval/`.

```
eval/
  manifests/<dataset>.json   one per dataset: source, licence, categories, ground truth, files, split rule, data pack
  splits/<dataset>.json      frozen dev / held-out page IDs per category (IDs only), with sha256 digests
  locks/<dataset>.lock.json  sizes and sha256 of every file fetch_pack wrote (no content)
  fetch_pack.py              sample-only download: just the pages the splits need (standard library only)
  export_dev.py              the development split as one zip, held-out never included
  download.py                whole-dataset download (WO-001; kept for small datasets)
  .data/                     git-ignored: raw/, gt/, index/, runs/, exports/
```

## On the owner's Windows PC (step by step)

The data is downloaded on your PC (O6). You do this once, then again whenever the orchestrator
asks. You need about **2 GB** of free disk space.

1. **Install Python.** Go to <https://www.python.org/downloads/windows/>, download the latest
   Python 3.13 "Windows installer (64-bit)", run it, tick **"Add python.exe to PATH"**, then click
   **Install Now**.
2. **Install Git.** Go to <https://git-scm.com/download/win>, download the installer and accept
   the defaults.
3. **Get the project.** Open the Start menu, type `cmd`, open **Command Prompt**, and run:
   ```
   cd %USERPROFILE%\Documents
   git clone https://github.com/strong0-23/ProjectIRIS.git
   cd ProjectIRIS
   ```
   (Already cloned? Run `cd %USERPROFILE%\Documents\ProjectIRIS` then `git pull`.)
4. **Fetch the data pack** (one command; it can take a while and can be re-run safely if it is
   interrupted):
   ```
   py eval\fetch_pack.py --all --accept-eval-only --archive-password bln600=<password>
   ```
   BLN600's publishers protect its archive with a password shown on the
   [dataset page](https://orda.shef.ac.uk/articles/dataset/BLN600_A_Parallel_Corpus_of_Machine_Human_Transcribed_Nineteenth_Century_Newspaper_Texts/25439023),
   next to its licence (CC BY-NC-ND 4.0). Read the licence there and put the password in place of
   `<password>` (or `set IRIS_BLN600_PASSWORD=<password>` first). It is never stored in the
   repository. Without it, BLN600 is skipped with a one-line message and everything else is
   fetched.
   It prints a short table at the end: pages per dataset, category and split, and how much was
   downloaded. A line `NOT FETCHED: ...` means a dataset failed; copy that line to the
   orchestrator. Nothing needs to be installed for this step.
5. **Install the harness requirements** (once):
   ```
   py -m pip install -r research\eval\requirements.txt
   ```
6. **Export the development split** (one command):
   ```
   py eval\export_dev.py --accept-eval-only
   ```
   It prints the size first, then writes `eval\.data\exports\iris-dev-<date>.zip`. That zip holds
   only development pages; hand it to the orchestrator. Add `--include-private` to include your
   own development photos (see "Your own photos" below). Never share the zip publicly.
7. **Commit the new split and lock files** (IDs and hashes only, no content): ask the Git agent,
   or tell the orchestrator they were created (`eval\splits\*.json`, `eval\locks\*.lock.json`).

Held-out pages stay on your PC. They are scored there (`--heldout-scoring-run`) and never
exported or opened by an agent.

## Quick start (any machine)

```bash
python eval/fetch_pack.py --list                       # datasets, licence use, estimated download
python eval/fetch_pack.py --all --accept-eval-only     # fetch every pack the licence gate allows
pip install -r research/eval/requirements.txt          # plus Tesseract 5 with eng for the baseline
export PYTHONPATH=research/eval
python -m iris_eval.prepare cord-v2                    # converts the split's pages, checks the frozen split
python eval/export_dev.py --accept-eval-only           # dev zip (prepares every fetched dataset first)
python eval/export_dev.py --import iris-dev.zip --data-dir <empty folder>   # receiving side (e.g. the sandbox)
python -m iris_eval.run_reader --reader tesseract --dataset pubtabnet-final-eval \
    --split dev --out eval/.data/runs/tesseract-dev/predictions
python -m iris_eval.score --predictions eval/.data/runs/tesseract-dev/predictions \
    --dataset pubtabnet-final-eval --split dev --out eval/.data/runs/tesseract-dev
```

`score` writes `results.json` (schema `iris-results/1`) and `summary.md`. Add `--private` to
`run_reader` and `score` to include the private slot.

## `fetch_pack.py`: sample-only download

For each dataset with a `pack` in its manifest:

1. **Licence gate** (O4): `excluded` is refused; `evaluation-only` needs `--accept-eval-only`;
   `evaluation-only-needs-decision` is refused until the owner decides. A source marked
   `password_required` needs its password at run time (`--archive-password <dataset>=<password>`
   or the variable named by `password_env`); without it the dataset is skipped. Manifests never
   hold a password (the validator refuses one).
2. **List the pages on offer** without opening any page: from the archive's directory (the list
   of member names, read with an HTTP range request), or from a small index file (COCO
   `test.json`, `OmniDocBench.json`, `final_eval.json`).
3. **Apply the split rule** and check it against `eval/splits/<dataset>.json` (written on the
   first run; a later difference stops the run).
4. **Fetch only the files of the dev and held-out pages**: one range request per archive member
   where the host allows it, one request per file for per-file hosts. A whole archive is fetched
   only where there is no other way: parquet shards (CORD), FUNSD (17 MB), or as a fallback when
   a host ignores range requests, and only up to `--max-whole-gb` (default 2) and the source's
   `whole_max_bytes`. Otherwise the run stops and says so.
5. **Lock**: the first run records each file's size and sha256 (and each remote archive's size
   and ETag, or figshare file id) in `eval/locks/<dataset>.lock.json`. Later runs verify against
   it: a damaged local file is fetched again and must match; a remote archive that changed is
   refused; new files need `--update-lock`. Each archive member's CRC-32 is also checked.
6. Writes `raw/<dataset>/pack.json` (`iris-pack/1`: the page list with categories, groups and
   a few attributes, and the files of each selected page by role) and prints the summary.

Archive members are stored under `raw/<dataset>/<source>/<member path>`; paths are checked for
Windows rules (no `..`, drive letters, reserved names such as `CON`, or `<>:"|?*`), and a path
longer than 120 characters is stored under `<source>/_long/<hash><ext>` to stay within Windows'
260-character limit.

## Datasets (manifests as of 23 Nov 2026)

Estimated download on the owner's PC with range requests working; pages per split once fetched
(dev / held-out per category, from the split rule and the documented dataset sizes).

| id | use | categories | download method | est. download | pages (dev / held-out) | converter |
|---|---|---|---|---|---|---|
| pubtabnet-final-eval | allowed | tables | `final_eval.json` whole + range reads into `final_eval.zip` | ~23 MB | 60 / 40 (frozen) | yes |
| cord-v2 | allowed | receipts | 2 parquet shards whole (test, validation) | ~476 MB | 45 / 30 | yes (pyarrow) |
| doclaynet | allowed | letters-and-reports | range reads into `DocLayNet_core.zip` and `DocLayNet_extra.zip` | ~70 MB | 45 / 30 | yes |
| fatura | allowed | invoices (synthetic) | range reads into `FATURA2.zip` (fallback: whole, 691 MB) | ~10 MB | 45 / 30, by template (30 / 20 templates) | yes |
| smartdoc2015-ch2 | allowed | phone-photos-hard | range reads into `testDataset.zip` (26.6 GB, never whole) | ~240 MB | 45 / 30, by document (21 / 14 documents) | yes |
| tabrecset | allowed | tables | figshare API, then range reads into the archive | ~60 MB | 45 / 30 | yes |
| olmocr-bench | allowed | book-or-scanned-pages, letters-and-reports, tables | no pack yet (needs a test-pass metric) | 0 | - | no |
| funsd | evaluation-only | forms | whole `dataset.zip` from GitHub (17 MB) | ~17 MB | 45 / 30 | yes |
| omnidocbench | evaluation-only | book-or-scanned-pages, letters-and-reports, screenshots | `OmniDocBench.json` whole + one request per page image | ~235 MB | up to 45 / 30 per category (English pages only) | yes |
| bln600 | evaluation-only | book-or-scanned-pages | figshare API, then range reads into the password-protected archive (password supplied at run time) | ~150 MB | 45 / 30 | yes |
| sroie, vrdu, ctdar2019, uvdoc | excluded | - | refused (no licence stated, O4) | - | - | - |

**Total estimated download: about 1.3 GB.** Worst case, if every host that may fall back to a
whole archive does so: about 2.2 GB plus the BLN600 archive (size unknown from here, capped at
2 GB), so at most about 4.2 GB. SmartDoc (26.6 GB), DocLayNet (35.5 GiB) and TabRecSet are never
downloaded whole.

Evaluation-only datasets (O4 amendment, 23 Nov 2026) are never trained on, never redistributed,
nothing from them is committed except IDs and numbers, and `score` reports them separately (their
categories carry `[evaluation-only]`).

## Licence gate (O4)

| use | meaning | fetch_pack.py / download.py |
|---|---|---|
| `allowed` | licence allows commercial use and redistribution | fetches |
| `evaluation-only` | non-commercial or no-redistribution licence, approved by the owner for evaluation only | needs `--accept-eval-only` |
| `evaluation-only-needs-decision` | as above, no owner decision yet | fetch_pack refuses |
| `excluded` | licence missing or unclear | refuses |

## Splits: `iris-split/1` and `iris-split/1-grouped`

`iris-split/1`, per (dataset, category): drop `split.exclude`; rank page IDs by
`sha256("<seed>:<dataset>:<page id>")`; keep the first `sample_per_category`; the first
`round(n * dev_fraction)` are **dev**, the rest **held-out**. Seed `iris-wo001`, dev fraction 0.6.
Sample sizes: 100 for PubTabNet (60 / 40), 75 elsewhere (45 / 30).

`iris-split/1-grouped` keeps pages that share a source on one side: groups are ranked by
`sha256("<seed>:<dataset>:group:<group>")`, the first `round(G * dev_fraction)` groups are dev,
and pages are then drawn by page hash from each side (`round(sample * dev_fraction)` dev, the rest
held-out). Used for FATURA (group = template) and SmartDoc (group = source document, found from
identical ground-truth files in the archive directory).

Both depend only on IDs and group labels, never on content. `prepare` and `fetch_pack` recompute
the split and fail if it differs from `eval/splits/<dataset>.json`. Changing a frozen split is an
orchestrator decision.

**Held-out pages are never read by agents** (AGENTS.md). `run_reader` and `score` refuse
`--split heldout` without `--heldout-scoring-run`, which is for reporting runs only. Every tool
prints counts, never document content, and results never contain text.

## Your own photos: `OCR_PRIVATE_DATA` (O7)

One private folder on your PC that you keep adding to, outside the repository:

```
%OCR_PRIVATE_DATA%\
  receipts\IMG_0412.jpg
  receipts\IMG_0412.gt.json          optional ground truth (or IMG_0412.jpg.gt.json)
  phone-photos-hard\IMG_0533.jpg
  .iris-split.json                    written by the harness: the frozen split of every photo
```

- Folders are the categories: `receipts`, `invoices`, `forms`, `letters-and-reports`, `tables`,
  `book-or-scanned-pages`, `screenshots`, `phone-photos-hard`. Other folders are skipped.
- Set the folder once: `setx OCR_PRIVATE_DATA "D:\IRIS-private"` (Windows; open a new Command
  Prompt afterwards) or `export OCR_PRIVATE_DATA=...`.
- **Split rule `iris-private/1`**: the first time the harness sees a photo it assigns it and
  writes the assignment to `.iris-split.json` inside that folder (never in the repository). Photos
  on the *seen list* go to dev; every other photo goes to dev when
  `int(sha256("iris-private/1:" + sha256(photo bytes))[:8], 16) < 0.6 * 2^32`, else held-out.
  Assignments never change, except that a held-out photo that later appears on the seen list
  moves to dev. A renamed or moved photo keeps its assignment.
- **Seen list**: photos agents already saw during SplitLah. A text file anywhere outside the
  repository, one entry per line: the photo's file name, `<category>/<file name>`, or its sha256;
  `#` starts a comment. Give its path with `OCR_PRIVATE_SEEN` (or `--seen-list` for `status`).
- Check counts (no file names are printed):
  `py -m iris_eval.private status` (with `PYTHONPATH=research\eval`).
- Photos without ground truth are assigned but not scored until a `.gt.json` exists.

### Ground truth for your photos

Either `iris-gt/1` (below; `id`, `dataset`, `category`, `split` and `image` can be left out) or a
**SplitLah owner reference**, detected automatically (or convert one explicitly with
`py -m iris_eval.private convert-splitlah ref.json --out IMG_0412.gt.json`).

SplitLah reference schema supported (`splitlah-ref/1`); every field except `items` is optional:

```json
{
  "schema": "splitlah-ref/1",
  "merchant": "Shop name",
  "currency": "SGD",
  "items": [
    {"name": "Chicken rice", "quantity": 2, "amount": 900}
  ],
  "charges": {"service": 90, "gst": 81, "tax": null, "discount": -100, "rounding": -1},
  "total": 1070
}
```

- Amounts are **integer cents** (a string of digits is accepted; `"9.00"` is refused).
  `items[].amount` is the line amount as printed.
- Accepted aliases: `merchant` | `store` | `shop` (string, or an object with `name`);
  item `name` | `description` | `item`, `quantity` | `qty`, `amount` | `amount_cents` |
  `total_cents` | `line_total`; `total` | `printed_total` | `total_cents` | `printedTotal`.
- `charges` is an object (`service` | `service_charge` | `svc`, `gst`, `tax` | `vat`, `discount`,
  `rounding`, `subtotal`) or a list of `{"type": ..., "amount": ...}`. Zero or missing charges are
  skipped; unknown charge types are ignored.
- Result: key-value ground truth only (`text` and `tables` not annotated): `merchant`; per item
  `item_name`, `item_quantity` (when given) and `item_amount` (key = item name); `service_charge`,
  `gst`, `tax`, `discount`, `rounding`, `subtotal`; `total`. Amounts become canonical two-decimal
  strings (`1070` -> `10.70`, `-100` -> `-1.00`).

## Categories

`receipts`, `invoices`, `forms`, `letters-and-reports`, `tables`, `book-or-scanned-pages`,
`screenshots`, `phone-photos-hard` (crumpled, torn, faded, low light, skewed, shadowed). A page
belongs to one category; capture conditions go in the GT's `conditions` list.

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
do not cost anything in CER. In a dev export, `image` is relative to the data directory.

What each converter produces (`research/eval/iris_eval/datasets/`): CORD rows of words and
item/total fields; DocLayNet PDF text cells; FATURA region text and invoice fields; SmartDoc and
BLN600 transcription lines in reading order; TabRecSet tables only; FUNSD entity text and
question -> answer pairs; OmniDocBench text in reading order plus tables; PubTabNet tables and
cell text. Each module's docstring gives the details.

## Checks (developers)

From the repository root (the mypy config adds `research/eval` to mypy's search path, so the
`eval/` scripts type-check without setting `MYPYPATH`):

```bash
cd research/eval && python -m pytest -q && cd ../..
ruff check --config research/eval/pyproject.toml research/eval eval/download.py eval/fetch_pack.py eval/export_dev.py
mypy --config-file research/eval/pyproject.toml -p iris_eval
mypy --config-file research/eval/pyproject.toml eval/fetch_pack.py eval/export_dev.py eval/download.py
```

## Metrics

Defined in `research/eval/iris_eval/` (each module's docstring) and recorded in
docs/DECISIONS.md E7: CER and WER (order-independent at line level, `iris-norm/1`
normalisation), reading order (CER in the reader's order plus a pairwise order score), TEDS and
TEDS-struct, key-value accuracy, silent errors (words, numbers, cells, key-values; visible =
flagged or confidence below the threshold, default 0.5), missed words, flag recall, false flags,
and cost (seconds per page, peak memory, model download size).
