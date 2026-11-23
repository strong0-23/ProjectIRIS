"""The seeded split rules ``iris-split/1`` and ``iris-split/1-grouped``.

``iris-split/1``, within one (dataset, category) group:

1. drop the page IDs listed in the manifest's ``split.exclude``;
2. rank the remaining IDs by ``sha256("<seed>:<dataset>:<page id>")`` (hex, ascending);
3. keep the first ``sample_per_category`` IDs (all of them when it is null);
4. the first ``round(n * dev_fraction)`` ranked IDs are ``dev``, the rest ``heldout``.

``iris-split/1-grouped`` is for datasets where several pages share a source (captures of one
document, renders of one template). It splits *groups*, so no group has pages on both sides:

1. drop excluded IDs; rank the groups by ``sha256("<seed>:<dataset>:group:<group>")``;
2. the first ``round(G * dev_fraction)`` groups are dev groups, the rest held-out groups;
3. rank the pages of each side by ``sha256("<seed>:<dataset>:<page id>")`` and keep the first
   ``round(sample * dev_fraction)`` dev pages and ``sample - that`` held-out pages (all when the
   sample is null).

Both rules depend only on the manifest, the page IDs and the group labels, never on page
content, so they are reproducible and cannot be tuned by looking at documents. The resulting ID
lists are frozen in ``eval/splits/<dataset>.json`` and re-checked on every ``prepare`` and every
``fetch_pack`` run.

Standard library only: ``eval/fetch_pack.py`` imports this module before anything is installed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

SPLIT_RULE = "iris-split/1"
GROUPED_RULE = "iris-split/1-grouped"
RULES = (SPLIT_RULE, GROUPED_RULE)


class SplitMismatch(RuntimeError):
    pass


def rank_key(seed: str, dataset: str, page_id: str) -> str:
    return hashlib.sha256(f"{seed}:{dataset}:{page_id}".encode()).hexdigest()


def split_ids(
    page_ids: Iterable[str],
    *,
    seed: str,
    dataset: str,
    dev_fraction: float,
    sample: int | None,
    exclude: Iterable[str] = (),
) -> dict[str, list[str]]:
    if not 0.0 < dev_fraction < 1.0:
        raise ValueError("dev_fraction must be between 0 and 1")
    excluded = set(exclude)
    ids = sorted(set(page_ids) - excluded)
    ranked = sorted(ids, key=lambda i: rank_key(seed, dataset, i))
    if sample is not None:
        ranked = ranked[:sample]
    n_dev = round(len(ranked) * dev_fraction)
    return {"dev": sorted(ranked[:n_dev]), "heldout": sorted(ranked[n_dev:])}


def split_grouped(
    page_groups: Mapping[str, str],
    *,
    seed: str,
    dataset: str,
    dev_fraction: float,
    sample: int | None,
    exclude: Iterable[str] = (),
) -> dict[str, Any]:
    """``iris-split/1-grouped``: ``page_groups`` maps page ID to its group label."""
    if not 0.0 < dev_fraction < 1.0:
        raise ValueError("dev_fraction must be between 0 and 1")
    excluded = set(exclude)
    pages = {p: g for p, g in page_groups.items() if p not in excluded}
    groups = sorted(set(pages.values()), key=lambda g: rank_key(seed, dataset, f"group:{g}"))
    if len(groups) < 2:
        raise ValueError(f"{dataset}: a grouped split needs at least 2 groups, found {len(groups)}")
    n_dev_groups = round(len(groups) * dev_fraction)
    dev_groups = set(groups[:n_dev_groups])

    def ranked(side: set[str]) -> list[str]:
        return sorted((p for p, g in pages.items() if g in side), key=lambda i: rank_key(seed, dataset, i))

    dev = ranked(dev_groups)
    held = ranked(set(groups) - dev_groups)
    if sample is not None:
        n_dev = round(sample * dev_fraction)
        dev, held = dev[:n_dev], held[: sample - n_dev]
    return {
        "dev": sorted(dev),
        "heldout": sorted(held),
        "dev_groups": len({pages[p] for p in dev}),
        "heldout_groups": len({pages[p] for p in held}),
    }


def list_digest(ids: Iterable[str]) -> str:
    """sha256 over the sorted IDs, one per line; recorded beside each frozen list."""
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def compute_splits(
    manifest: dict[str, Any],
    pages: list[tuple[str, str]],
    groups: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Apply the manifest's split rule to ``pages`` ((native id, category) pairs)."""
    sp = manifest["split"]
    if sp["rule"] not in RULES:
        raise ValueError(f"unknown split rule {sp['rule']!r}")
    by_cat: dict[str, list[str]] = {}
    for nid, cat in pages:
        by_cat.setdefault(cat, []).append(nid)
    common: dict[str, Any] = {
        "seed": sp["seed"],
        "dataset": manifest["id"],
        "dev_fraction": float(sp["dev_fraction"]),
        "sample": sp["sample_per_category"],
        "exclude": sp["exclude"],
    }
    if sp["rule"] == GROUPED_RULE:
        if groups is None:
            raise ValueError(f"{manifest['id']}: rule {GROUPED_RULE} needs a group for every page")
        missing = [nid for nid, _ in pages if nid not in groups]
        if missing:
            raise ValueError(f"{manifest['id']}: {len(missing)} pages have no group")
        return {
            cat: split_grouped({i: groups[i] for i in ids}, **common)
            for cat, ids in sorted(by_cat.items())
        }
    return {cat: split_ids(ids, **common) for cat, ids in sorted(by_cat.items())}


def frozen_record(manifest: dict[str, Any], splits: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sp = manifest["split"]
    rec: dict[str, Any] = {
        "dataset": manifest["id"],
        "rule": sp["rule"],
        "seed": sp["seed"],
        "dev_fraction": sp["dev_fraction"],
        "sample_per_category": sp["sample_per_category"],
        "excluded_ids": len(sp["exclude"]),
    }
    if sp["rule"] == GROUPED_RULE:
        rec["group_by"] = sp.get("group_by")
    cats: dict[str, Any] = {}
    for cat, s in splits.items():
        c: dict[str, Any] = {
            "dev": s["dev"],
            "heldout": s["heldout"],
            "dev_sha256": list_digest(s["dev"]),
            "heldout_sha256": list_digest(s["heldout"]),
        }
        if "dev_groups" in s:
            c["dev_groups"] = s["dev_groups"]
            c["heldout_groups"] = s["heldout_groups"]
        cats[cat] = c
    rec["categories"] = cats
    return rec


def check_frozen(record: dict[str, Any], splits_dir: Path, write: bool) -> str:
    path = splits_dir / f"{record['dataset']}.json"
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            frozen = json.load(f)
        if frozen != record:
            raise SplitMismatch(
                f"{path} differs from the split recomputed from the manifest and data; "
                "the data or the manifest changed. Do not overwrite without an orchestrator decision."
            )
        return "matches frozen split"
    if not write:
        raise SplitMismatch(f"no frozen split {path}; run prepare with --write-splits once")
    splits_dir.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=1)
        f.write("\n")
    return "frozen split written"


def frozen_ids(splits_dir: Path, dataset: str) -> dict[str, set[str]] | None:
    """The frozen dev and held-out IDs of a dataset (all categories), or None when not frozen."""
    path = splits_dir / f"{dataset}.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        rec = json.load(f)
    out: dict[str, set[str]] = {"dev": set(), "heldout": set()}
    for c in rec["categories"].values():
        out["dev"].update(c["dev"])
        out["heldout"].update(c["heldout"])
    return out
