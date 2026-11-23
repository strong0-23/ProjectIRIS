"""FUNSD scanned forms (``annotations/<id>.json``: ``form`` entities with text, label, box, linking).

Text ground truth = each entity's text (an entity is a field label, a filled-in value, a header
or other text), top to bottom then left to right; no reading-order claim. Key-values = every
question -> answer link (key = question text, value = answer text).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._pack import PackConverter, page, pair


def funsd_gt(ann: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    form = [e for e in ann.get("form") or [] if isinstance(e, dict)]
    by_id = {e.get("id"): e for e in form}

    def pos(e: dict[str, Any]) -> tuple[float, float]:
        b = e.get("box") or [0, 0, 0, 0]
        return (float(b[1]), float(b[0]))

    lines = [" ".join(str(e["text"]).split()) for e in sorted(form, key=pos) if str(e.get("text") or "").strip()]
    links: set[tuple[Any, Any]] = set()
    for e in form:
        for link in e.get("linking") or []:
            if len(link) != 2:
                continue
            a, b = (by_id.get(x) for x in link)
            if a is None or b is None:
                continue
            if a.get("label") == "answer" and b.get("label") == "question":
                a, b = b, a
            if a.get("label") == "question" and b.get("label") == "answer":
                links.add((a.get("id"), b.get("id")))
    pairs = [p for q, a in sorted(links, key=str) if (p := pair(by_id[q].get("text"), None, by_id[a].get("text")))]
    return lines, pairs


class Funsd(PackConverter):
    def convert(self, raw: Path, native_id: str) -> dict[str, Any]:
        lines, pairs = funsd_gt(self.read_json(raw, native_id, "annotation"))
        return page(self.file(raw, native_id, "image"), lines=lines, pairs=pairs, conditions=["noisy-scan"],
                    attrs=self.attrs(raw, native_id))
