from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def word(text: str, conf: float | None = 0.9, flags: list[str] | None = None) -> dict[str, Any]:
    """A document-model word for synthetic predictions."""
    w: dict[str, Any] = {"text": text}
    if conf is not None:
        w["confidence"] = conf
    if flags:
        w["flags"] = flags
    return w


def doc(*blocks: dict[str, Any], source: dict[str, Any] | None = None) -> dict[str, Any]:
    """A one-page document-model JSON with the given blocks."""
    d: dict[str, Any] = {"pages": [{"width": 100, "height": 100, "blocks": list(blocks)}], "issues": []}
    if source is not None:
        d["source"] = source
    return d


def para(*lines: list[dict[str, Any]] | str, order: int | None = None,
         flags: list[str] | None = None) -> dict[str, Any]:
    """A paragraph block; each line is a string (line text) or a list of words."""
    out_lines: list[dict[str, Any]] = []
    for ln in lines:
        if isinstance(ln, str):
            out_lines.append({"text": ln, "confidence": 0.9})
        else:
            out_lines.append({"words": ln})
    b: dict[str, Any] = {"type": "paragraph", "lines": out_lines}
    if order is not None:
        b["order"] = order
    if flags:
        b["flags"] = flags
    return b
