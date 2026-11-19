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
