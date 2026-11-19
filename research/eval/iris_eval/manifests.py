"""Dataset manifests (``eval/manifests/<id>.json``, schema ``iris-manifest/1``).

See eval/README.md for the fields. ``use`` decides what the tools may do with a dataset:

- ``allowed``: licence fits docs/DECISIONS.md O4; may be downloaded and scored.
- ``evaluation-only-needs-decision``: licence forbids commercial use or redistribution, so it can
  never ship; scoring it needs an owner decision (O4) and ``--accept-eval-only``.
- ``excluded``: licence missing or unclear; the tools refuse it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import MANIFEST_DIR

MANIFEST_SCHEMA = "iris-manifest/1"
USES = ("allowed", "evaluation-only-needs-decision", "excluded")
REQUIRED = (
    "id",
    "name",
    "homepage",
    "licence",
    "commercial_use",
    "redistribution",
    "use",
    "categories",
    "ground_truth",
    "size",
    "files",
    "split",
    "download_status_here",
)


class ManifestError(ValueError):
    pass


def validate_manifest(m: dict[str, Any]) -> dict[str, Any]:
    if m.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError(f"{m.get('id')}: schema must be {MANIFEST_SCHEMA}")
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        raise ManifestError(f"{m.get('id')}: missing {missing}")
    if m["use"] not in USES:
        raise ManifestError(f"{m['id']}: use must be one of {USES}")
    lic = m["licence"]
    for k in ("name", "url", "read_at"):
        if not lic.get(k):
            raise ManifestError(f"{m['id']}: licence.{k} is required")
    sp = m["split"]
    for k in ("rule", "seed", "dev_fraction", "sample_per_category", "exclude"):
        if k not in sp:
            raise ManifestError(f"{m['id']}: split.{k} is required")
    for f in m["files"]:
        if not f.get("url") or not f.get("dest"):
            raise ManifestError(f"{m['id']}: every file needs url and dest")
        if "/" in f["dest"] or "\\" in f["dest"] or f["dest"].startswith("."):
            raise ManifestError(f"{m['id']}: dest must be a plain file name")
    return m


def load_manifest(dataset: str, manifest_dir: Path = MANIFEST_DIR) -> dict[str, Any]:
    path = manifest_dir / f"{dataset}.json"
    if not path.is_file():
        raise ManifestError(f"no manifest {path}")
    with path.open(encoding="utf-8") as f:
        m = json.load(f)
    if m.get("id") != dataset:
        raise ManifestError(f"{path}: id {m.get('id')!r} does not match file name")
    return validate_manifest(m)


def list_manifests(manifest_dir: Path = MANIFEST_DIR) -> list[dict[str, Any]]:
    return [load_manifest(p.stem, manifest_dir) for p in sorted(manifest_dir.glob("*.json"))]
