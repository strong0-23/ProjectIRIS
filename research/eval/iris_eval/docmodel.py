"""Read a reader's output in the IRIS document model (docs/MODULES.md) for scoring.

The harness reads one JSON ``Document`` per page and uses its first page. It is tolerant of
optional fields so early candidates can be scored before the model is final:

- Blocks are taken in ``order`` (list position when ``order`` is missing).
- A block's text comes from its ``lines``; a table block without lines contributes its cells in
  row-major order, one line per cell; a key-value block without lines contributes ``key value``.
- A word is *flagged* when it, its line or its block carries a non-empty ``flags`` list.
- A word's confidence is its own, else its line's, else its block's; ``None`` when no level gives
  one (treated as confident: a reader that reports no confidence cannot hide behind it).
- Cost comes from ``source``: ``timings.totalSeconds``, ``peakMemoryBytes`` and
  ``models[].sizeBytes``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .gt import Cell, Pair, Table
from .normalize import words as split_words


@dataclass(frozen=True)
class PredWord:
    text: str
    confidence: float | None
    flagged: bool


@dataclass(frozen=True)
class PredLine:
    text: str
    words: tuple[PredWord, ...]


@dataclass
class Cost:
    seconds: float | None = None
    peak_memory_bytes: int | None = None
    models: dict[str, int | None] = field(default_factory=dict)


@dataclass
class PredPage:
    lines: list[PredLine]
    tables: list[Table]
    pairs: list[Pair]
    cost: Cost
    declared_threshold: float | None = None


class DocModelError(ValueError):
    """Raised when a prediction is not a readable IRIS document."""


def _flagged(obj: dict[str, Any]) -> bool:
    flags = obj.get("flags")
    return isinstance(flags, list) and len(flags) > 0


def _conf(obj: dict[str, Any]) -> float | None:
    c = obj.get("confidence")
    return float(c) if isinstance(c, (int, float)) else None


def _text(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("text", ""))
    return "" if v is None else str(v)


def _line(line: dict[str, Any], block_conf: float | None, block_flag: bool) -> PredLine:
    line_conf = _conf(line)
    conf = line_conf if line_conf is not None else block_conf
    flag = block_flag or _flagged(line)
    raw_words = line.get("words")
    pw: list[PredWord] = []
    if isinstance(raw_words, list) and raw_words:
        for w in raw_words:
            wc = _conf(w)
            for token in split_words(_text(w)):
                pw.append(PredWord(token, wc if wc is not None else conf, flag or _flagged(w)))
        text = " ".join(_text(w) for w in raw_words)
    else:
        text = _text(line)
        pw = [PredWord(t, conf, flag) for t in split_words(text)]
    if line.get("text") is not None:
        text = str(line["text"])
    return PredLine(text=text, words=tuple(pw))


def _table(t: dict[str, Any], block_conf: float | None, block_flag: bool) -> Table:
    cells = []
    for c in t.get("cells", []):
        cc = _conf(c)
        cells.append(
            Cell(
                row=int(c["row"]),
                col=int(c["col"]),
                row_span=int(c.get("rowSpan", 1)),
                col_span=int(c.get("colSpan", 1)),
                text=_text(c),
                confidence=cc if cc is not None else block_conf,
                flagged=block_flag or _flagged(c),
            )
        )
    return Table(tuple(cells))


def parse_document(doc: dict[str, Any]) -> PredPage:
    pages = doc.get("pages")
    if not isinstance(pages, list):
        raise DocModelError("document has no pages list")
    page: dict[str, Any] = pages[0] if pages else {"blocks": []}
    blocks = page.get("blocks", [])
    if not isinstance(blocks, list):
        raise DocModelError("page.blocks must be a list")
    indexed = list(enumerate(blocks))
    indexed.sort(key=lambda ib: (ib[1].get("order", ib[0]), ib[0]))

    lines: list[PredLine] = []
    tables: list[Table] = []
    pairs: list[Pair] = []
    for _, b in indexed:
        b_conf = _conf(b)
        b_flag = _flagged(b)
        table = None
        if isinstance(b.get("table"), dict):
            table = _table(b["table"], b_conf, b_flag)
            tables.append(table)
        block_pairs: list[Pair] = []
        for p in b.get("pairs") or []:
            pc = _conf(p)
            block_pairs.append(
                Pair(
                    key=_text(p.get("key")) or None,
                    field=p.get("field"),
                    value=_text(p.get("value")),
                    confidence=pc if pc is not None else b_conf,
                    flagged=b_flag or _flagged(p),
                )
            )
        pairs.extend(block_pairs)
        if isinstance(b.get("lines"), list) and b["lines"]:
            lines.extend(_line(ln, b_conf, b_flag) for ln in b["lines"])
        elif table is not None:
            for c in sorted(table.cells, key=lambda c: (c.row, c.col)):
                lines.append(
                    PredLine(c.text, tuple(PredWord(t, c.confidence, c.flagged) for t in split_words(c.text)))
                )
        elif block_pairs:
            for p in block_pairs:
                t = f"{p.key or ''} {p.value}".strip()
                lines.append(PredLine(t, tuple(PredWord(w, p.confidence, p.flagged) for w in split_words(t))))

    src = doc.get("source") or {}
    timings = src.get("timings") or {}
    seconds = timings.get("totalSeconds")
    mem = src.get("peakMemoryBytes")
    models: dict[str, int | None] = {}
    for m in src.get("models") or []:
        size = m.get("sizeBytes")
        models[str(m.get("name", "?"))] = int(size) if isinstance(size, (int, float)) else None
    thr = src.get("confidenceThreshold")
    return PredPage(
        lines=lines,
        tables=tables,
        pairs=pairs,
        cost=Cost(
            seconds=float(seconds) if isinstance(seconds, (int, float)) else None,
            peak_memory_bytes=int(mem) if isinstance(mem, (int, float)) else None,
            models=models,
        ),
        declared_threshold=float(thr) if isinstance(thr, (int, float)) else None,
    )
