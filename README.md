# Project IRIS

An open-source OCR engine for printed documents of any kind.

Point it at a receipt, an invoice, a form, a letter, a report, a table, or a page from a book or a
screen. Scanned or taken with a phone. Crumpled, torn, faded or shot in bad light. It should give
you back what is on the page and how it is laid out: headings, paragraphs, tables, key-value pairs
and the order to read them in. Every piece comes with its position, a confidence score and a flag
when it needs checking. Output is JSON and Markdown.

English printed documents first. Handwriting and other languages come later.

## Why

This started with SplitLah, my bill-splitting app. Its receipt scanner was tuned on a handful of
receipts and looked fine on those. On receipts it had never seen, it did badly. Fixing the rules
for each new receipt does not scale, and it never gets you a scanner that copes with the next one.

So I am building a general engine and judging it only on documents it has never seen. SplitLah
can use it later.

## Principles

- **Your documents stay with you.** It runs in the browser on your phone or computer with nothing
  uploaded, or as a local service on a machine you control. No cloud OCR or AI API.
- **Never silent.** When it is unsure, it flags it instead of guessing.
- **Moddable.** Every stage is a plug-in. Swap a model, fine-tune one, or replace a stage with your
  own code.
- **Our own engine, open parts.** We write the engine. The models inside it are open ones.
- **Lightweight and modular.** Small pieces with clear jobs.
- **Free to run.** No paid services.
- **Open.** Apache 2.0, and every model and dataset it uses must allow commercial use.

If your mother can use it, anyone can.

## Status

Planning. Nothing is built yet.

The first milestone is an evaluation set and a scoring harness, so every choice is judged on
unseen documents. Then a bake-off of open models: the latest PaddleOCR, docTR, Granite-Docling,
GLM-OCR, PaddleOCR-VL and Florence-2, with Tesseract as the baseline. No engine code until both
are done.

## How it's built

I decide and review, with Claude in a planning chat. Together we are the orchestrator. Agents carry
out the work: a Git agent handles git and GitHub, and Claude Code is the coding agent. Test and
design agents come later. We tell and it executes.

Each task is a GitHub issue labelled [`wo`](../../issues?q=label%3Awo).

- [docs/WORKFLOW.md](docs/WORKFLOW.md): who does what, and how work gets reviewed and merged
- [docs/DECISIONS.md](docs/DECISIONS.md): what was decided and why
- [docs/MODULES.md](docs/MODULES.md): the planned architecture and document model

## Licence

[Apache License 2.0](LICENSE).
