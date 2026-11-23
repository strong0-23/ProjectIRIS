"""Converters from each dataset's native ground truth to ``iris-gt/1``.

A converter lists the pages it can provide (native ID and IRIS category) without reading
their ground truth, then converts single pages on request. Datasets fetched by
``eval/fetch_pack.py`` list their pages from ``raw/<dataset>/pack.json`` (``_pack.PackConverter``)
and may also give ``page_groups(raw)`` for grouped splits. Only pages chosen by the split rule are
ever converted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .bln600 import Bln600
from .cord_v2 import CordV2
from .doclaynet import DocLayNet
from .fatura import Fatura
from .funsd import Funsd
from .omnidocbench import OmniDocBench
from .pubtabnet_final_eval import PubTabNetFinalEval
from .smartdoc2015 import SmartDoc2015
from .tabrecset import TabRecSet


class Converter(Protocol):
    def list_pages(self, raw: Path) -> list[tuple[str, str]]: ...

    def convert(self, raw: Path, native_id: str) -> dict[str, Any]: ...


CONVERTERS: dict[str, type[Any]] = {
    "pubtabnet_final_eval": PubTabNetFinalEval,
    "cord_v2": CordV2,
    "doclaynet": DocLayNet,
    "fatura": Fatura,
    "smartdoc2015": SmartDoc2015,
    "tabrecset": TabRecSet,
    "funsd": Funsd,
    "omnidocbench": OmniDocBench,
    "bln600": Bln600,
}


def get_converter(name: str | None) -> Converter:
    if not name or name not in CONVERTERS:
        raise KeyError(
            f"no converter {name!r}; a converter is written once the dataset can be downloaded "
            "and its format checked"
        )
    conv: Converter = CONVERTERS[name]()
    return conv
