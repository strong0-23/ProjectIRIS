"""Candidate readers. Each turns one page image into an IRIS document (docs/MODULES.md).

A reader has ``name``, ``describe() -> dict`` (version, models, settings) and
``read(image: Path) -> dict`` (the document). Readers run in research only; the engine has its
own stage interfaces.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .tesseract import TesseractReader


class Reader(Protocol):
    name: str

    def describe(self) -> dict[str, Any]: ...

    def read(self, image: Path) -> dict[str, Any]: ...


READERS: dict[str, type[Any]] = {"tesseract": TesseractReader}


def get_reader(name: str) -> Reader:
    if name not in READERS:
        raise KeyError(f"unknown reader {name!r}; known: {sorted(READERS)}")
    reader: Reader = READERS[name]()
    return reader
