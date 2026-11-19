# WO-001 report: evaluation set and scoring harness

Coding agent, 19 Nov 2026, branch `wo/001-eval-harness`. Issue #1.

## Outcome against the acceptance line

| Acceptance item | Status |
|---|---|
| Every dataset's licence recorded; nothing outside O4 committed or shipped | **Met.** 14 manifests, each with licence name, URL and date read. No dataset files are committed; only manifests, scripts and one frozen list of page IDs. |
| Splits fixed and reproducible from the manifests | **Met** for the one dataset downloadable here (PubTabNet final eval: 60 dev / 40 held-out, frozen and re-checked). The rule is in every manifest; the other lists get frozen on first download. |
| Harness unit tests with synthetic inputs for every metric, including silent errors | **Met.** 55 tests, all synthetic, all passing. |
| Tesseract baseline on the development split, per category | **Partly met.** Tables only (60 dev pages). The other categories have no O4-clear data reachable from this sandbox. See "Decisions" (1, pending owner). |

## What was built

- `eval/manifests/*.json` (14): source, licence, `use` (allowed / evaluation-only-needs-decision /
  excluded), categories, ground-truth types, size, files with checksums, split parameters, download
  status here.
- `eval/download.py`: standard library only. Fetches, verifies size and sha256/md5, unpacks with
  path-traversal and link checks, enforces the licence gate, reports unreachable hosts.
- `eval/splits/pubtabnet-final-eval.json`: frozen dev and held-out page IDs with digests.
- `eval/README.md`: layout, quick start, licence gate, split rule, private slot, GT format.
- `research/eval/iris_eval/`: the harness (normalisation, GT and document-model readers, text and
  reading-order metrics, TEDS, key-values, silent errors, cost, split rule, index, private slot,
  PubTabNet converter, Tesseract reader, `prepare` / `run_reader` / `score` commands).
- `research/eval/tests/`: 55 unit tests.
- `docs/DECISIONS.md`: E6 (evaluation set, licence gate, splits) and E7 (metric definitions).
- `docs/MODULES.md`: the document-model fields the harness relies on, and the harness modules.

Dependencies (licences checked against O4): rapidfuzz 3.14.6 (MIT), apted 1.0.3 (MIT),
Pillow 12.3.0 (MIT-CMU); dev: pytest (MIT), ruff (MIT), mypy (MIT). Tesseract 5.3.4 (Apache-2.0) is
called as an external program. pytesseract is not used: calling the CLI directly lets the reader
measure the Tesseract process's peak memory.

## Datasets

Network from this sandbox: GitHub (including raw, codeload and LFS media), PyPI and npm reachable;
Hugging Face, Zenodo, Google Drive, figshare, RRC, github.io, IBM COS/DAX, Kaggle, archive.org and
the project hosts below were refused by the proxy. No mirrors or workarounds were tried.

| Dataset | Source | Data licence (where read) | Redistribution | Categories | Ground truth | Pages per split | Downloaded here |
|---|---|---|---|---|---|---|---|
| PubTabNet final eval (ICDAR 2021 task B) | github.com/ajjimeno/icdar-task-b @86a9c80 | Annotations CDLA-Permissive-1.0; images PMC OA commercial-use terms ([LICENSE.md](https://github.com/ibm-aur-nlp/PubTabNet/blob/master/LICENSE.md)) | Annotations yes; images with per-article attribution. Not redistributed (IDs only committed). Repo has no licence file; covered by PubTabNet's licence as its own test set (orchestrator decision) | tables | table structure + cell text (HTML); text in row-major cell order | **60 dev / 40 held-out** (sample of 9,064; 17 excluded) | **yes** (223 MB, checksums verified) |
| CORD v2 | huggingface.co/datasets/naver-clova-ix/cord-v2 | CC BY 4.0 ([github.com/clovaai/cord](https://github.com/clovaai/cord)) | yes | receipts (phone photos; Indonesian/English) | words, boxes, semantic key-values | planned 45 / 30 | no: host not reachable from the sandbox |
| DocLayNet | IBM COS (codait-cos-dax) | CDLA-Permissive-1.0 ([HF card](https://huggingface.co/datasets/ds4sd/DocLayNet-v1.1/blob/main/README.md)) | yes | letters-and-reports (financial, laws, tenders, manuals, patents) | layout boxes, PDF text cells; no reading order | planned 45 / 30 | no: host not reachable |
| FATURA | zenodo.org/records/10371464 | CC BY 4.0 ([Zenodo](https://zenodo.org/records/10371464)) | yes | invoices (**synthetic**, 50 templates) | words, boxes, 24 field classes | planned 45 / 30 | no: host not reachable |
| SmartDoc 2015 Challenge 2 | zenodo.org/record/2572929 | CC BY 4.0 ([Zenodo](https://zenodo.org/record/2572929)) | yes | phone-photos-hard (blur, perspective, lighting) | document text | planned 45 / 30, split by source document | no: host not reachable (38.8 GB) |
| TabRecSet | figshare 10.6084/m9.figshare.20647788 | CC BY-SA 4.0 ([github.com/MaxKinny/TabRecSet](https://github.com/MaxKinny/TabRecSet)) | yes, share-alike | tables, phone-photos-hard (English subset) | table structure, cell text, boxes | planned 45 / 30 per category | no: host not reachable |
| olmOCR-Bench | huggingface.co/datasets/allenai/olmOCR-bench | ODC-BY-1.0 ([HF card](https://huggingface.co/datasets/allenai/olmOCR-bench)) | yes | book-or-scanned-pages, letters-and-reports, tables | unit tests only (presence, absence, order, table neighbours) | not set: needs a test-pass metric | no: host not reachable |
| FUNSD | guillaumejaume.github.io/FUNSD | Non-commercial research and education only ([terms](https://guillaumejaume.github.io/FUNSD/work)) | no | forms | words, boxes, key-values | planned 45 / 30 | no: host not reachable; also needs a decision |
| OmniDocBench | huggingface.co/datasets/opendatalab/OmniDocBench | Research only, not commercial ([HF card](https://huggingface.co/datasets/opendatalab/OmniDocBench)) | no | book-or-scanned-pages, letters-and-reports, tables, screenshots (slides) | text, reading order, tables, boxes | planned 45 / 30 per category | no: host not reachable; also needs a decision |
| BLN600 | ORDA (Sheffield) | CC BY-NC-ND 4.0 ([ORDA](https://orda.shef.ac.uk/articles/dataset/BLN600_A_Parallel_Corpus_of_Machine_Human_Transcribed_Nineteenth_Century_Newspaper_Texts/25439023)) | unmodified, non-commercial | book-or-scanned-pages (19th-c. newspapers) | transcriptions | planned 45 / 30 | no: host not reachable; also needs a decision |
| SROIE | rrc.cvc.uab.es/?ch=13 | **none stated** | unknown | receipts | text lines, boxes, 4 fields | excluded: no licence stated (O4) | no |
| VRDU | github.com/google-research-datasets/vrdu | **none stated** (no LICENSE, none in README) | unknown | forms | field values (text is machine OCR) | excluded: no licence stated (O4) | no (host reachable) |
| ICDAR 2019 cTDaR | github.com/cndplab-founder/ICDAR2019_cTDaR | **none stated** | unknown | tables | structure only, no cell text | excluded: no licence stated (O4) | no (host reachable) |
| UVDoc benchmark | igl.ethz.ch/projects/uvdoc | **none stated** | unknown | phone-photos-hard | not confirmed | excluded: no licence stated (O4) | no |

Licences marked as permitted (O4): CC BY 4.0 (CORD, FATURA, SmartDoc 2015 Ch2),
CDLA-Permissive-1.0 (PubTabNet annotations, DocLayNet), ODC-BY-1.0 (olmOCR-Bench),
CC BY-SA 4.0 (TabRecSet; evaluation only, nothing shipped). Each URL above is where the licence was
read on 19 Nov 2026.

**Gaps.** No O4-clear dataset found for **screenshots** or **letters** (DocLayNet has reports but
no letters); **forms** have only FUNSD (non-commercial) and VRDU (no licence); **book or scanned
pages** have only olmOCR-Bench (unit tests, ODC-BY) and non-commercial sets.

### Hard-condition photos (for the owner)

- Available here: **0 dev / 0 held-out.** Nothing with photos was reachable.
- From public data once downloaded: SmartDoc 2015 (planned 45 dev / 30 held-out; blur, perspective
  and lighting on flat pages) and TabRecSet (planned 45 / 30; deformed and skewed tables).
  CORD receipts are phone photos but their conditions are not labelled.
- No O4-clear public set covers **crumpled, torn, faded or shadowed receipts and documents** with
  text ground truth. To get 30 held-out pages on those, the owner needs about **75 own photos
  (45 dev / 30 held-out)**, ideally 10–15 per condition (crumpled, torn, faded, low light, skewed,
  shadowed) if per-condition numbers are wanted.

## Tesseract baseline (development split)

Tesseract 5.3.4, `eng`, `--psm 3`, default engine, no preprocessing; confidence threshold 0.5.
CPU sandbox, 2 cores. Command: `tesseract <image> stdout -l eng --psm 3 tsv`.

Silent errors first (E7), then visible errors and other scores:

| Category | Dev pages | Silent words | Silent numbers | Silent cells | Wrong words (visible + silent) | Flag recall | False flags | Missed words | CER | WER | CER in reader order | Order score | TEDS | TEDS-struct | s/page mean (p50 / p95) | Peak memory | Model size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tables | 60 | 3.1% | 3.0% | 0.0% | 15.7% | 80.5% | 38.7% | 81.1% | 87.4% | 96.8% | 87.6% | 0.884 | 0.000 | 0.000 | 0.20 (0.14 / 0.51) s | 40 MB | 4.1 MB |
| receipts, invoices, forms, letters-and-reports, book-or-scanned-pages, screenshots, phone-photos-hard | 0 | not run: no O4-clear data reachable here | | | | | | | | | | | | | | | |

How to read it:
- PubTabNet images are small table crops (dev widths 155–761 px, median 486) at screen
  resolution. Tesseract returned **no text at all on 16 of 60** and garbled text on most of the rest;
  81% of ground-truth words are missed. I checked dev pages by hand: on one page the harness gives
  41% CER, which matches the output. These are real baseline numbers, not a harness fault.
  Upscaling would help, but that is preprocessing for the bake-off, not tuning a baseline.
- TEDS is 0 because Tesseract outputs no tables. Silent cells are 0% for the same reason: no
  cells were produced, so none can be wrong.
- Silent words are low (3.1%) mainly because most words are missed, and 80% of wrong words fall
  below the 0.5 threshold. 38.7% of correct words are also below it (false flags).
- `results.json` and `summary.md` are in `eval/.data/runs/tesseract-dev/` (git-ignored, IDs and
  numbers only).

## Checks run

| Check | Result |
|---|---|
| `pytest` (research/eval, 55 tests: normalisation, CER/WER, order, TEDS and HTML parsing, key-values, silent words/numbers/cells/key-values, document-model parsing, splits and frozen-split checks, private slot (synthetic files; results contain no text), missing predictions, aggregation, Tesseract TSV mapping, Tesseract end to end on a synthetic image, PubTabNet converter, download verify/unpack/licence gate/traversal/unreachable host, all repo manifests) | 55 passed |
| `ruff check research/eval eval/download.py` | passed |
| `mypy --strict` on `iris_eval` (20 files) and on `eval/download.py` | no issues |
| `eval/download.py pubtabnet-final-eval` (real) | both files verified against pinned sha256 and size; unpacked |
| `eval/download.py` on a refused host (smartdoc2015-ch2) | reports "host zenodo.org not reachable", exit 3 |
| `eval/download.py` gates (sroie excluded, funsd eval-only, fatura unpinned) | each refused with its reason |
| `prepare pubtabnet-final-eval` run twice | first writes the frozen split, second "matches frozen split" (60 / 40) |
| Excluded IDs absent from both splits | 0 in dev, 0 in held-out |
| `run_reader` / `score` with `--split heldout` and no flag | refused, exit 2 |
| Tesseract baseline on dev | 60/60 pages read, 0 failures, scored |

Not checked: mypy on the test files (not strict-typed); the harness on Windows (peak memory needs
POSIX `wait4` and is recorded as missing elsewhere); converters for the 12 datasets I could not
download (none written: their formats can't be checked here); anything on held-out (not run, as
the task says).

## Incident: ground truth seen before the split

While inspecting the PubTabNet test repository, `git show` printed the start of `final_eval.json`:
I expected a Git LFS pointer and got the real file. Ground truth for **17 tables** was shown to
me before any split existed. I listed those IDs from what was displayed and excluded them from
both splits (`split.exclude` in the manifest, with the reason). The check above confirms none are
in dev or held-out. No other dataset content was viewed. Only dev pages were inspected afterwards.

## Decisions

Pending owner:

1. **Pending owner. The baseline covers tables only.** Every O4-clear dataset for the other
   categories sits on a host this sandbox can't reach. Options: (a) the owner runs
   `python eval/download.py --all`, pins the printed checksums, and the next task writes
   converters and runs the baseline on a machine that can reach Hugging Face, Zenodo, figshare
   and IBM COS; (b) widen the sandbox allowlist to those hosts.
2. **Pending owner. Evaluation-only datasets (O4):** use FUNSD (forms), OmniDocBench (books,
   slides, reports) and BLN600 (old newspapers) for evaluation only, never shipped? They are the
   only sources found for forms, screenshot-like slides and book pages with full text ground truth.

Settled by the orchestrator (WO-001 review, 19 Nov 2026):

3. **Datasets with no stated licence are dropped.** SROIE, VRDU, cTDaR and UVDoc stay `excluded`,
   reason "no licence stated (O4)".
4. **PubTabNet final eval is covered by PubTabNet's licence**, as PubTabNet's own test set. Only
   page IDs are committed. Recorded in the manifest's licence note.
5. **No combined error score.** Every acceptance line names silent and visible errors separately,
   silent errors first (E7).

## Limitations and follow-ups

- Possible contamination: public test sets may be in candidates' training data. Private held-out
  pages are the only guaranteed-unseen data.
- olmOCR-Bench needs a unit-test metric (presence, absence, order, table neighbours).
- TEDS here has no thead/tbody nodes and compares normalised text, so it is close to, but not
  directly comparable with, published PubTabNet TEDS.
- CORD is mixed Indonesian/English (O1 is English first); report it separately.
- SmartDoc's converter must keep all captures of one document in the same split.
