# Decisions

Significant choices and why. Newest at the bottom of each section. A decision changes only by a new
entry that says what it replaces.

## Owner decisions at kickoff (17 Nov 2026)

### O1: Scope: an OCR engine for any document, receipts included
**Rule.** The engine reads printed documents of any kind and returns their structure, not only
their text: receipts, invoices, forms, letters, reports, tables, book and screen pages, as scans
or as phone photos, including crumpled, torn, faded and low-light ones.
**Not yet.** Handwriting and languages other than English. Both are planned future options, so
nothing may assume English-only or print-only where a plug-in could add them later.
**Why.** SplitLah showed that a receipt-only parser tuned on a few receipts does not generalise.
A general engine, measured on unseen documents, is the better foundation; SplitLah can use it
later.

### O2: Runs in the browser and on a machine the owner controls
**Rule.** One engine, two runtimes:
- **Browser** (phone or desktop): fully on the device, no upload. WebGPU when available, WASM
  otherwise.
- **Server**: a local service on a machine the owner controls (his PC or any self-hosted box).
Recognition never calls a cloud OCR or AI API.
**Why.** Owner decision: both runtimes, open source, nothing leaves the user's control.

### O3: Output is structure
**Rule.** The engine returns a document model (pages → blocks such as heading, paragraph, list,
table, key-value, figure → lines → words) with positions, confidence and review flags, and
exports it to JSON and Markdown. Plain text is one export of that model, not the product.

### O4: Public repository, Apache 2.0
**Rule.** The code is public under Apache 2.0. Every model, dataset and dependency we ship or
download must carry a licence that allows commercial use and redistribution without revenue
caps, field-of-use limits or non-commercial clauses (Apache 2.0, MIT, BSD, CC BY, CDLA-Permissive
and the like). OpenRAIL-style weights with revenue triggers (e.g. Surya, Chandra) and
non-commercial datasets are excluded from what we ship. A non-commercial dataset may be used for
evaluation only if its licence allows that, and is never redistributed.
**Why.** Public and moddable, and safe to build a product on later.

### O5: Free only
**Rule.** No paid services: no paid GPU, hosting or API. Evaluation and any training run on free
compute: Claude's sandbox (CPU), the owner's PC (an NVIDIA GPU with 16 GB of VRAM), or free tiers
whose terms allow it. Models that need more than 16 GB of VRAM to be usable are out of scope for
now. The agents' shell on the owner's PC runs in a small Linux machine without the GPU, so GPU runs
are started on Windows by the owner, or by Claude Code running there.
**Why.** Owner decision. It also keeps the engine usable by anyone who forks it.

## Engineering decisions at kickoff (orchestrator, 17 Nov 2026)

### E1: Our engine, open parts
**Rule.** We write the engine: its stages, interfaces, verification and document model. Each
stage is a plug-in behind a small interface, and the first plug-ins wrap existing open models.
A stage can be replaced by a different model, a fine-tuned one, or our own code without
touching the other stages.
**Why.** Building every model from scratch would need training data and compute we do not have
(O5) and would trail open models for a long time. Owning the engine and its interfaces is what
makes it moddable.

### E2: Measure first, on unseen documents
**Rule.** Before engine code, we build an evaluation set and a scoring harness. The set has a
development split (may be read and diagnosed) and a held-out split (never read by any agent, used
only to report results). Every model choice and every change to how documents are read is judged
on the held-out split before it is adopted. Rules or settings shaped around single documents are
not accepted.
**Why.** SplitLah's development receipts showed 40–60% while unseen receipts showed 0%.

### E3: Never silent
**Rule.** When the engine is unsure of a word, a number, a cell or a block, it says so (low
confidence plus a review flag with a reason) rather than presenting a guess as fact. Silent
errors (wrong output with no flag) are scored separately and weigh more than visible errors.
**Why.** Users act on what the engine returns. A visible doubt costs a glance; a silent error
costs trust.

### E4: Stack, provisional until the bake-off
**Rule.**
- **Engine:** TypeScript, one codebase for both runtimes. Models run through ONNX Runtime
  (`onnxruntime-web` in the browser with WebGPU/WASM, `onnxruntime-node` on the server).
- **Research:** Python, in `research/` only: running candidate models in their native form for
  the bake-off, scoring, converting models to ONNX, and any fine-tuning.
**Why.** One language for the engine that ships in both runtimes; Python where the model
ecosystem is. Confirmed or revised after WO-002, depending on which candidates convert to ONNX.

### E5: Orchestrator, Git agent, coding agent
**Rule.** Work runs through the roles in `docs/WORKFLOW.md`. The orchestrator (the owner with
Claude in his planning chat) decides each task and reviews every result. The Git agent carries out
all git and GitHub operations on instruction. The coding agent builds one task at a time and hands
back for review; it does not commit or touch GitHub. GitHub issues are the task list. The owner
approves each milestone and every gated task, and receives a short review of every finished task.
A test agent and a design agent are planned.
**Why.** Owner decision (19 Nov 2026): agents are simple executors; "we tell and it executes", and
the owner and Claude review the work.
