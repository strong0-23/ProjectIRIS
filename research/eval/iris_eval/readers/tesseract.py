"""Tesseract baseline reader (Apache-2.0), run as the ``tesseract`` command-line program.

Command per page: ``tesseract <image> stdout -l eng --psm 3 tsv`` (fully automatic page
segmentation, default engine mode). The TSV hierarchy maps onto the document model as:
paragraph -> ``paragraph`` block (in Tesseract's order), line -> line, word -> word with
``confidence = conf / 100``. Tesseract emits no tables, key-values or flags, so those scores
show what a plain text reader gets: TEDS 0 on tables, every wrong word above the threshold silent.

Cost: wall seconds around the call; peak memory is the ``tesseract`` process's maximum resident
set size from ``os.wait4`` (POSIX only; ``None`` elsewhere); model size is the ``eng.traineddata``
file.
"""

from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PSM = 3
LANG = "eng"


class TesseractError(RuntimeError):
    pass


class TesseractReader:
    name = "tesseract"

    def __init__(self, binary: str | None = None, lang: str = LANG, psm: int = PSM) -> None:
        found = binary or shutil.which("tesseract")
        if not found:
            raise TesseractError("tesseract binary not found on PATH")
        self.binary = found
        self.lang = lang
        self.psm = psm
        self._describe: dict[str, Any] | None = None

    def describe(self) -> dict[str, Any]:
        if self._describe is None:
            ver = subprocess.run([self.binary, "--version"], capture_output=True, text=True)
            version_line = (ver.stdout or ver.stderr).splitlines()[0].strip()
            langs = subprocess.run([self.binary, "--list-langs"], capture_output=True, text=True)
            m = re.search(r'"([^"]+)"', langs.stdout + langs.stderr)
            model = Path(m.group(1)) / f"{self.lang}.traineddata" if m else None
            size = model.stat().st_size if model and model.is_file() else None
            self._describe = {
                "reader": self.name,
                "version": version_line,
                "command": [Path(self.binary).name, "<image>", "stdout", "-l", self.lang,
                            "--psm", str(self.psm), "tsv"],
                "models": [{"name": f"tesseract-{self.lang}", "version": version_line,
                            "sizeBytes": size, "licence": "Apache-2.0"}],
            }
        return self._describe

    def _tsv(self, image: Path) -> tuple[str, int | None]:
        cmd = [self.binary, str(image), "stdout", "-l", self.lang, "--psm", str(self.psm), "tsv"]
        if not hasattr(os, "wait4"):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise TesseractError(r.stderr.strip()[:500])
            return r.stdout, None
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err)
            assert proc.stdout is not None
            out = proc.stdout.read()
            proc.stdout.close()
            _, status, ru = os.wait4(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
            if proc.returncode != 0:
                err.seek(0)
                raise TesseractError(err.read().decode(errors="replace").strip()[:500])
        # ru_maxrss is KiB on Linux, bytes on macOS.
        peak = ru.ru_maxrss if sys.platform == "darwin" else ru.ru_maxrss * 1024
        return out.decode("utf-8", errors="replace"), peak

    def read(self, image: Path) -> dict[str, Any]:
        t0 = time.perf_counter()
        tsv, peak = self._tsv(image)
        doc = tsv_to_document(tsv)
        doc["source"] = {
            "runtime": "research-python",
            "models": self.describe()["models"],
            "timings": {"totalSeconds": time.perf_counter() - t0},
            "peakMemoryBytes": peak,
        }
        return doc


def _box(r: dict[str, str]) -> list[int]:
    x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
    return [x, y, x + w, y + h]


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def tsv_to_document(tsv: str) -> dict[str, Any]:
    """Convert Tesseract TSV output into an IRIS document with one page."""
    rows = list(csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE))
    width = height = 0
    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    lines: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        level = r.get("level")
        if level == "1":
            width, height = int(r["width"]), int(r["height"])
        elif level == "3":
            blocks[(r["block_num"], r["par_num"])] = {
                "type": "paragraph", "box": _box(r), "order": len(blocks),
                "confidence": None, "flags": [], "lines": [],
            }
        elif level == "4":
            ln: dict[str, Any] = {"text": "", "box": _box(r), "confidence": None, "flags": [], "words": []}
            lines[(r["block_num"], r["par_num"], r["line_num"])] = ln
            blocks[(r["block_num"], r["par_num"])]["lines"].append(ln)
        elif level == "5":
            text = (r.get("text") or "").strip()
            conf = float(r["conf"])
            if not text or conf < 0:
                continue
            lines[(r["block_num"], r["par_num"], r["line_num"])]["words"].append(
                {"text": text, "box": _box(r), "confidence": conf / 100.0}
            )
    out_blocks: list[dict[str, Any]] = []
    for b in blocks.values():
        kept = []
        for ln in b["lines"]:
            if not ln["words"]:
                continue
            ln["text"] = " ".join(w["text"] for w in ln["words"])
            ln["confidence"] = _mean([w["confidence"] for w in ln["words"]])
            kept.append(ln)
        if kept:
            b["lines"] = kept
            b["confidence"] = _mean([ln["confidence"] for ln in kept])
            b["order"] = len(out_blocks)
            out_blocks.append(b)
    return {
        "pages": [{"width": width, "height": height, "quality": None, "blocks": out_blocks}],
        "issues": [],
    }
