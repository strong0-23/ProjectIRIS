"""Converters from each dataset's native ground truth to ``iris-gt/1``.

A converter lists the pages it can provide (native ID and IRIS category) without reading
their ground truth, then converts single pages on request. Only pages chosen by the split rule are
ever converted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .pubtabnet_final_eval import PubTabNetFinalEval


class Converter(Protocol):
    def list_pages(self, raw: Path) -> list[tuple[str, str]]: ...

    def convert(self, raw: Path, native_id: str) -> dict[str, Any]: ...


CONVERTERS: dict[str, type[Any]] = {
    "pubtabnet_final_eval": PubTabNetFinalEval,
}


def get_converter(name: str | None) -> Converter:
    if not name or name not in CONVERTERS:
        raise KeyError(
            f"no converter {name!r}; a converter is written once the dataset can be downloaded "
            "and its format checked"
        )
    conv: Converter = CONVERTERS[name]()
    return conv
