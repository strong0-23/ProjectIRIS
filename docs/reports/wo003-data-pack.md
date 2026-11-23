# WO-003 report: PC data pack and owner photos

Coding agent, 23 Nov 2026, branch `wo/003-data-pack` (from `origin/main` 2b4962b). Issue #4.

## Outcome against the acceptance line

| Acceptance item | Status |
|---|---|
| Every allowed and approved evaluation-only dataset has a complete manifest and a converter, or a stated reason it can't | **Met, with two manifests resolved at run time.** 9 of 10 have a pack and a converter. olmOCR-Bench: manifest completed (test files, commit, page addressing); no converter, reason stated (unit-test ground truth needs a test-pass metric; PDFs need a rasteriser). TabRecSet and BLN600: figshare could not be read from here, so their archive name and size are resolved from the figshare API on the first run and pinned in the lock (the run stops with the file list if the pattern does not match exactly one archive). |
| `fetch_pack.py` and `export_dev.py` pass tests with a local fake server and fake archives, including a Windows-path test | **Met.** 101 tests pass (46 new for WO-003, 2 updated for the O7 layout), all synthetic. |
| Estimated download per dataset and total, under 10 GB or a stated reason | **Met: about 1.3 GB** (worst case with every allowed whole-archive fallback about 4.2 GB). |
| No dataset content, owner photo or private path in the diff | **Met.** Only manifests (URLs, sizes, hashes from the hosts' pages), code, synthetic tests and docs. |

## Owner decisions recorded

`docs/DECISIONS.md`: O4 amendment (FUNSD, OmniDocBench, BLN600 evaluation-only), O6 (data
access), O7 (owner photos), as worded in the issue. FUNSD, OmniDocBench and BLN600 now have
`use: evaluation-only`.

## What was built

- **`eval/fetch_pack.py`** (standard library only; a test runs it with site-packages disabled).
  Licence gate, page listing per dataset (`iris_eval/pack/planners.py`), split rule, frozen-split
  check (written on the first run), fetch of the split's files only, lock, `pack.json`, one-screen
  summary. Range reads go through `RemoteFile`, a seekable file over HTTP `Range` that `zipfile`
  reads like a local file (CRC-32 checked per member). Retries with backoff; whole-archive fallback
  only within caps; Windows-safe paths (reserved names, `<>:"|?*`, `..`, drive letters, 260-char
  limit via hashed names over 120 characters); console output cannot crash on a file name.
- **Locks** `eval/locks/<dataset>.lock.json` (`iris-lock/1`): size + sha256 per file written,
  URL/size/ETag or figshare id per source. Verified on every run; damaged files re-fetched and
  re-verified; changed sources refused; new files need `--update-lock`.
- **Converters** to `iris-gt/1` (`iris_eval/datasets/`): `cord_v2`, `doclaynet`, `fatura`,
  `smartdoc2015`, `tabrecset`, `funsd`, `omnidocbench`, `bln600` (PubTabNet's existing one is
  reused unchanged). Packed datasets list pages from `pack.json` so `prepare` reproduces the split.
- **Grouped split** `iris-split/1-grouped` (FATURA by template, SmartDoc by document). The split
  helpers moved from `index.py` to `splits.py` (stdlib) unchanged; a test confirms the frozen
  PubTabNet record is reproduced byte for byte.
- **`eval/export_dev.py`** (+ `iris_eval/export.py`): prepares fetched datasets, prints the size
  estimate, writes one zip of dev pages (data-directory layout, relative paths), `--dry-run`,
  `--include-private`, `--accept-eval-only`, and `--import` with safe extraction on the receiving
  side. Stops if any page is outside its frozen dev list or its GT is not marked dev.
- **Private slot (O7)** `iris_eval/private.py`: layout `OCR_PRIVATE_DATA/<category>/<photo>` +
  optional `<stem>.gt.json` (or `<file>.gt.json`); rule `iris-private/1`; frozen
  `.iris-split.json` inside the private folder; seen list (`OCR_PRIVATE_SEEN` / `--seen-list`;
  names, relative paths or sha256); `status` (counts only); SplitLah reference converter
  (auto-detected in `.gt.json`, or `convert-splitlah`). Schema documented in `eval/README.md`.
- **Scoring**: evaluation-only datasets are aggregated under `<category> [evaluation-only]`
  (O4 amendment), never mixed with O4-clear data.
- **Docs**: `eval/README.md` (Windows guide for a non-developer, fetch/lock/export, datasets table,
  splits, private slot, SplitLah schema), `eval/locks/README.md`, `docs/MODULES.md` (pack, export,
  private contracts), `docs/DECISIONS.md` (O4 amendment, O6, O7; E8-E12 for review).

## Datasets

Estimated download on the owner's PC with range requests working. Pages per split are what the
split rule gives on the documented dataset sizes once fetched (sample 75 = 45 / 30; PubTabNet 100).

| Dataset | Use | Manifest complete? | Converter? | Download method | Est. download | Pages once fetched (dev / held-out) |
|---|---|---|---|---|---|---|
| pubtabnet-final-eval | allowed | yes (pinned sha256, sizes) | yes (WO-001) | `final_eval.json` whole + range reads into `final_eval.zip` (fallback: whole zip, pinned) | ~23 MB | tables 60 / 40 (frozen, unchanged) |
| cord-v2 | allowed | yes (commit 7f0115a, sha256 of both shards; byte sizes recorded on first run) | yes (needs pyarrow) | 2 parquet shards whole (test 234 MB, validation 242 MB) | ~476 MB | receipts 45 / 30 (of 200) |
| doclaynet | allowed | yes (URLs; sizes/ETags recorded on first run) | yes | range reads into core and extra zips (COCO test.json, PNG, cell JSON); never whole | ~70 MB | letters-and-reports 45 / 30 (of 4,999) |
| fatura | allowed | yes (Zenodo API URL, 690,717,658 bytes, md5) | yes | range reads into `FATURA2.zip` (fallback: whole, 691 MB) | ~10 MB | invoices 45 / 30, 30 / 20 templates (of 10,000) |
| smartdoc2015-ch2 | allowed | yes (Zenodo API URL, md5); member naming undocumented | yes | range reads into `testDataset.zip` (26.6 GB); never whole | ~240 MB | phone-photos-hard 45 / 30, 21 / 14 documents (of 8,470) |
| tabrecset | allowed | file resolved at run time (figshare unreadable here) | yes | figshare API, then range reads; never whole | ~60 MB (unverified) | tables 45 / 30 (English originals); phone-photos-hard 0 (no condition labels) |
| olmocr-bench | allowed | yes (7 test files at commit 54a96a6, page addressing) | **no**: unit-test GT + PDFs (reason in manifest) | no pack yet | 0 | - |
| funsd | evaluation-only | yes (GitHub commit 8905aca, 16,838,830 bytes) | yes | whole `dataset.zip` | ~17 MB | forms 45 / 30 (of 199) |
| omnidocbench | evaluation-only | yes (commit aa1ee96, sha256 of `OmniDocBench.json`) | yes | JSON whole + one request per page image | ~235 MB | up to 45 / 30 each for book-or-scanned-pages, letters-and-reports, screenshots (English pages; counts per category not known until fetched) |
| bln600 | evaluation-only | file resolved at run time (figshare unreadable here) | yes | figshare API, then range reads into the password-protected ZipCrypto archive; password supplied at run time, never stored (fallback: whole, up to 2 GB) | ~150 MB (unverified) | book-or-scanned-pages 45 / 30 (of 600) |
| sroie, vrdu, ctdar2019, uvdoc | excluded | unchanged | - | refused | - | - |

**Total estimated download: ~1.28 GB** (sum of the manifests' estimates: 1,280,838,830 bytes).
Worst case if PubTabNet, FATURA and BLN600 all fall back to whole archives: about 2.2 GB plus the
BLN600 archive (size unknown, capped at 2 GB), at most about 4.2 GB. Real figures per dataset are
printed by the first run and recorded in the locks.

Sources of the numbers: CORD sizes and sha256 and OmniDocBench commit/sha256 from the Hugging Face
file pages; FATURA size and md5 from its Zenodo page and public code that range-reads this exact
URL; SmartDoc md5 and counts from Zenodo and the competition paper; DocLayNet layout from its
README on GitHub; FUNSD size and commit from GitHub. Per-page sizes are estimates (archive size /
pages).

### Real-host check from the sandbox

Range reads against GitHub-hosted archives, directory only (file names, no member opened):
- FUNSD `dataset.zip` (raw.githubusercontent.com): 16.8 MB archive, 809 entries, **155 KB fetched
  in 3 requests**; the planner pairs **199 forms** (149 training + 50 testing). The archive
  contains `__MACOSX/` copies, which the planners skip.
- PubTabNet `final_eval.zip` (media.githubusercontent.com): 203.6 MB, 9,064 entries at the root,
  **1.1 MB fetched in 3 requests**. This is why PubTabNet now uses range reads (~23 MB instead of
  223 MB).

## Checks run

| Check | Result |
|---|---|
| `pytest` (research/eval): 101 tests. New: fetch end to end with a local range server (FATURA-like grouped pack: only 20 of 200 pages fetched, lock written then verified, damaged file re-fetched, prepare reproduces the frozen split), remote change refused, no-range fallback under/over cap, licence gate (excluded, eval-only flag, needs-decision, no pack), lock rules, planners for DocLayNet (two archives, redundant annotations), SmartDoc (groups from GT CRC, wrong document count stops), BLN600 (ZipCrypto archive built with `zip -P` and a synthetic password, figshare API, wrong password stops, password from the environment, missing password skips with a one-line pointer before any network access, from the library and the CLI; a manifest holding a password is refused), figshare ambiguity, OmniDocBench (per-file, language and category filter), CORD (parquet built with pyarrow), FUNSD (whole), PubTabNet (exclude list), TabRecSet (English originals only), layout mismatch stops; Windows paths (reserved names, invalid characters, `PureWindowsPath` joins, 260-char limit, `/` lock keys); `fetch_pack.py` with site-packages disabled; converters; private slot (rule fraction, freeze, seen list, seen-after-assignment, rename, unknown folders, counts without names, SplitLah full/minimal/invalid, CLI); export (dev only, held-out in a corrupted index stops it, eval-only and private flags, import round trip, unsafe or held-out members refused, CLI dry run); frozen PubTabNet record unchanged; grouped split | **101 passed** |
| `ruff check --config research/eval/pyproject.toml research/eval eval/download.py eval/fetch_pack.py eval/export_dev.py` (repo root) | passed |
| `mypy --config-file research/eval/pyproject.toml -p iris_eval` (repo root; strict via the config) | no issues in 37 files |
| `mypy --config-file research/eval/pyproject.toml eval/fetch_pack.py eval/export_dev.py eval/download.py` (repo root, no `MYPYPATH`) | no issues in 3 files |
| `python -S -I eval/fetch_pack.py --list` (standard library only) | lists 14 datasets with use, pack and estimate |
| Range reads on real GitHub hosts (directory only) | see above |
| `git diff` scan for private paths, names, dataset content | none found |

## Not checked

- **No real pack was fetched**: Hugging Face, Zenodo, figshare and IBM COS are refused here, and
  O6 keeps held-out pages off the sandbox. The first real run on the owner's PC is the real test.
- **Range support** of Zenodo, IBM COS and figshare's file host: not verifiable here. FATURA's URL is
  range-read by public code; IBM COS is S3-compatible. Each source fails loudly or falls back within
  its cap.
- **Archive layouts not verified**: SmartDoc test (naming undocumented; images and text paired by
  stem, documents by identical GT file), TabRecSet (folder names from the paper; archive name from
  a pattern), BLN600 (folder names from the dataset page; ZipCrypto assumed, AES would stop the run
  with a message; the password is supplied by the owner at run time), DocLayNet (from its README), FATURA annotation keys (from public code). Every
  planner stops with counts when the layout differs, never guesses.
- Converter output on real files (all converters are tested on synthetic records shaped like the
  documented formats only).
- The scripts on real Windows (tested with Windows path rules on Linux only); the guide's steps
  were not run on Windows.
- OmniDocBench pages per category (depends on the English pages per data source).

## Decisions

Settled by the orchestrator (WO-003 review, 23 Nov 2026):

1. **pyarrow 26.0.1 approved (E12):** research-only, imported only by the CORD converter,
   Apache-2.0, not a runtime, framework or model under the WORKFLOW gate.
2. **E8-E11 accepted**, and the private slot layout change (`<category>/<photo>` with rule-based
   splits; nothing used the WO-001 layout).
3. **The BLN600 archive password is not republished.** The publishers show it on their page so
   that users read the licence first. The person running `fetch_pack` supplies it at run time
   (`--archive-password bln600=<password>` or `IRIS_BLN600_PASSWORD`); without it BLN600 is skipped
   with a one-line pointer to the dataset page and licence. Manifests that hold a password are
   refused by the validator.

No decision is pending. No licence, cost or compute question arose.

## Limitations and follow-ups

- TabRecSet gives no phone-photos-hard pages (no capture labels); hard-condition photos come from
  SmartDoc and the owner's photos.
- olmOCR-Bench needs a test-pass metric and a PDF rasteriser before it can have a pack.
- SplitLah-converted amounts are canonical two-decimal strings; key-value scoring compares
  normalised text, so readers must output amounts in that form to match.
- FATURA field values include the printed label when there is no `:` to split on.
- OmniDocBench inline formulas stay as LaTeX in the text ground truth.
