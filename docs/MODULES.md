# Modules

Planned architecture. Nothing here is built yet; the evaluation harness and the model bake-off come
first (docs/DECISIONS.md E2). Contracts are provisional until the bake-off (WO-002) confirms which models fill each stage.

## Pipeline

```
image or PDF page
  → prepare     crop, straighten, de-warp, fix lighting; quality report (blur, dark, glare, cut off)
  → detect      text line regions
  → recognise   text and per-character confidence for each line
  → layout      block types and reading order
  → structure   tables (rows, cells, spans) and key-value pairs
  → read-heavy  optional: a document model reads the page end to end
  → verify      compare readers, run format and arithmetic checks, set confidence and flags
  → export      JSON (the document model) and Markdown
```

`read-heavy` is optional per runtime and per device. When it runs, `verify` reconciles it with
the fast path; when they disagree, the disagreement is flagged, never resolved silently (E3).

## Layout of the code

```
packages/core/       document model, stage interfaces, pipeline, verify, export — pure TypeScript,
                     no DOM, no Node APIs, no model runtime; unit-tested with synthetic input
packages/runtime-web/   ONNX Runtime Web adapters (WebGPU, WASM), canvas image I/O
packages/runtime-node/  ONNX Runtime Node adapters, file I/O, local HTTP service
packages/models/     model manifests: source, licence, version, checksum, input/output spec
research/            Python: candidate runners, scoring, ONNX conversion, fine-tuning
eval/                manifests and download scripts for evaluation data — never the data itself
                     unless its licence allows redistribution, and never private documents
```

Rules:
- `core` imports no runtime, DOM, Node or model SDK code. Stages reach models through
  interfaces; adapters live in the runtime packages.
- A stage is replaceable without touching other stages.
- Model files are fetched from their published source and pinned by checksum; they are not
  committed.

## Document model (provisional)

```
Document  { pages: Page[], issues: Issue[], source: { runtime, models[], timings } }
Page      { width, height, quality: QualityReport, blocks: Block[] }
Block     { type: heading | paragraph | list | table | keyValue | figure | other,
            box, order, confidence, flags: Flag[], lines?: Line[], table?: Table, pairs?: Pair[] }
Line      { text, box, confidence, flags: Flag[], words: Word[] }
Word      { text, box, confidence }
Table     { rows, cols, cells: { row, col, rowSpan, colSpan, text, box, confidence, flags }[] }
Flag      { reason: low-confidence | readers-disagree | check-failed | cut-off | … , detail }
```

Coordinates are in page pixels of the prepared image, with the transform back to the original
image recorded so callers can draw on the photo the user took.

### Fields the evaluation harness reads (WO-001, provisional)

The harness (`research/eval/iris_eval/docmodel.py`) scores any reader that writes this model, one
`Document` per page image. It relies on these details, which the model above leaves open:

```
box       [x0, y0, x1, y1] in page pixels
Pair      { key, value, field?, box?, confidence, flags }   key/value: string or { text, box }
          field: optional canonical name (e.g. "total") when the reader knows it
Word      { text, box, confidence, flags? }                 flags optional; line/block flags apply to its words
Cell      { row, col, rowSpan, colSpan, text, box?, confidence?, flags? }
confidence  0..1; missing confidence is treated as confident (cannot hide an error)
source    { runtime, models: [{ name, version, sizeBytes, licence }],
            timings: { totalSeconds, <stage>Seconds... }, peakMemoryBytes, confidenceThreshold? }
```

Text is taken from block `lines` in block `order`; a table block without lines contributes its
cells row by row, and a key-value block without lines contributes `key value` per pair, so a block
must not repeat text another block already holds.

## Evaluation harness (research/eval)

Research-only Python package `iris_eval`; never imported by the engine.

```
eval/manifests/*.json --fetch_pack.py (pack planner + split rule; locks in eval/locks/)--> eval/.data/raw/<dataset>/
                                                                    (only the split's files + pack.json)
     (download.py: whole files, WO-001)
     --prepare (converter + split rule, checked against eval/splits/)--> eval/.data/gt/, index/
     --export_dev.py (dev only)--> eval/.data/exports/iris-dev-<date>.zip --import--> another data dir
     --run_reader (reader -> Document JSON per page)--> <run>/predictions/<dataset>/<key>.json
     --score--> <run>/results.json (iris-results/1) + summary.md
```

| Module | Job | Contract |
|---|---|---|
| `normalize` | text normalisation `iris-norm/1` | pure functions |
| `gt` | page ground truth `iris-gt/1` (eval/README.md) | `parse_gt(dict) -> PageGT` |
| `docmodel` | read a reader's `Document` | `parse_document(dict) -> PredPage` |
| `textmetrics`, `teds`, `kv`, `silent` | metrics | pure functions on `PageGT` / `PredPage` parts |
| `splits`, `index`, `manifests` | split rules `iris-split/1` and `iris-split/1-grouped`, frozen splits, page index (paths may be relative to the data dir), manifests (incl. `pack`) | `compute_splits(manifest, pages, groups)`, `prepare(dataset)`, `load_index(dataset)` |
| `pack/*` | data packs, **standard library only**: safe paths, HTTP + range-read `RemoteFile`, locks, sources, per-dataset planners, the fetch run | `fetch_dataset(manifest, ...) -> Result`; planner `(Context) -> [Page]` |
| `private` | `OCR_PRIVATE_DATA` slot (O7): `<category>/<photo>`, rule `iris-private/1`, frozen `.iris-split.json`, seen list, SplitLah converter | `load_private(split, root?, seen?) -> [IndexEntry]`, `sync_assignments(root, seen)`, `splitlah_to_gt(ref)` |
| `export` | dev-split export and import | `plan_export(datasets, ...) -> Plan`, `write_export(plan, out)`, `import_export(zip, data_root)` |
| `datasets/*` | native GT -> `iris-gt/1`, one converter per dataset; packed datasets list pages from `pack.json` (`_pack.PackConverter`) | `list_pages(raw)`, `convert(raw, id)`, optional `page_groups(raw)` |
| `readers/*` | candidate readers | `describe() -> dict`, `read(image) -> Document` |
| `score`, `run_reader`, `prepare` | command-line entry points | see eval/README.md |

Results never contain document text, only IDs and numbers. Held-out pages need an explicit
`--heldout-scoring-run` flag. Pages of evaluation-only datasets are aggregated under
`<category> [evaluation-only]` (DECISIONS E11).

Data owned per location (WO-003): `eval/manifests`, `eval/splits`, `eval/locks` (committed, IDs and
hashes only); `eval/.data/raw/<dataset>/pack.json`, fetched files, `gt/`, `index/`, `exports/`
(owner's PC, git-ignored); `OCR_PRIVATE_DATA/.iris-split.json` (private folder only).
Contract change: the private slot layout moved from `dev|heldout/<category>/` to `<category>/`
with a rule-based frozen split (O7); `load_private(split)` keeps its signature.
