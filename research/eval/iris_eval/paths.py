"""Where things live. Data never lives in git: everything downloaded or derived goes under the
data directory (default ``eval/.data/``, git-ignored; override with ``IRIS_EVAL_DATA``)."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = REPO_ROOT / "eval" / "manifests"
SPLITS_DIR = REPO_ROOT / "eval" / "splits"
PRIVATE_ENV = "OCR_PRIVATE_DATA"


def data_dir() -> Path:
    env = os.environ.get("IRIS_EVAL_DATA")
    return Path(env).resolve() if env else REPO_ROOT / "eval" / ".data"


def raw_dir(dataset: str) -> Path:
    return data_dir() / "raw" / dataset


def gt_dir(dataset: str) -> Path:
    return data_dir() / "gt" / dataset


def index_path(dataset: str) -> Path:
    return data_dir() / "index" / f"{dataset}.jsonl"


def safe_key(native_id: str) -> str:
    """File-system-safe key for a page (used for GT and prediction file names)."""
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in native_id)
