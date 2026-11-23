"""Dataset manifests (``eval/manifests/<id>.json``, schema ``iris-manifest/1``).

See eval/README.md for the fields. ``use`` decides what the tools may do with a dataset:

- ``allowed``: licence fits docs/DECISIONS.md O4; may be downloaded and scored.
- ``evaluation-only``: licence forbids commercial use or redistribution, so it can never ship;
  approved by the owner for evaluation only (O4 amendment, 23 Nov 2026): never trained on, never
  redistributed, reported separately, and the tools need ``--accept-eval-only``.
- ``evaluation-only-needs-decision``: as above, but no owner decision yet; ``fetch_pack`` refuses it.
- ``excluded``: licence missing or unclear; the tools refuse it.

``pack`` (optional) describes the sample-only download used by ``eval/fetch_pack.py``: a
``planner`` (``iris_eval.pack.planners``), its ``sources`` and an ``estimate``. A fetchable
dataset without a pack gives the reason in ``pack_reason``.

Standard library only (imported by ``eval/fetch_pack.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .pack.planners import PLANNERS
from .pack.sources import KINDS
from .paths import MANIFEST_DIR

MANIFEST_SCHEMA = "iris-manifest/1"
USES = ("allowed", "evaluation-only", "evaluation-only-needs-decision", "excluded")
EVAL_ONLY_USES = ("evaluation-only", "evaluation-only-needs-decision")
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
    _validate_pack(m)
    return m


def _validate_pack(m: dict[str, Any]) -> None:
    pack = m.get("pack")
    if not pack:
        if m["use"] in ("allowed", "evaluation-only") and not m.get("pack_reason"):
            raise ManifestError(f"{m['id']}: a fetchable dataset needs a pack or a pack_reason")
        return
    if pack.get("planner") not in PLANNERS:
        raise ManifestError(f"{m['id']}: unknown pack planner {pack.get('planner')!r}")
    names = [s.get("name") for s in pack.get("sources", [])]
    if not names or len(set(names)) != len(names) or not all(names):
        raise ManifestError(f"{m['id']}: pack sources need unique names")
    for s in pack["sources"]:
        if s.get("kind") not in KINDS:
            raise ManifestError(f"{m['id']}: source {s.get('name')}: kind must be one of {KINDS}")
        need = {"file": ("url", "dest"), "zip": ("url",), "url-files": ("base_url",),
                "figshare-zip": ("article", "file_regex")}[s["kind"]]
        for k in need:
            if not s.get(k):
                raise ManifestError(f"{m['id']}: source {s['name']} needs {k}")
        if "password" in s:
            raise ManifestError(f"{m['id']}: source {s['name']}: never store an archive password in a manifest")
        if s.get("password_required") and not s.get("password_env"):
            raise ManifestError(f"{m['id']}: source {s['name']}: password_required needs password_env")
        dest = s.get("dest")
        if dest and ("/" in dest or "\\" in dest or dest.startswith(".")):
            raise ManifestError(f"{m['id']}: source {s['name']}: dest must be a plain file name")
    if not (pack.get("estimate") or {}).get("bytes"):
        raise ManifestError(f"{m['id']}: pack.estimate.bytes is required")


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
