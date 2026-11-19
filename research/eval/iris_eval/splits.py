"""The seeded split rule ``iris-split/1``.

Within one (dataset, category) group:

1. drop the page IDs listed in the manifest's ``split.exclude``;
2. rank the remaining IDs by ``sha256("<seed>:<dataset>:<page id>")`` (hex, ascending);
3. keep the first ``sample_per_category`` IDs (all of them when it is null);
4. the first ``round(n * dev_fraction)`` ranked IDs are ``dev``, the rest ``heldout``.

The rule depends only on the manifest and the page IDs, never on page content, so it is
reproducible and cannot be tuned by looking at documents. The resulting ID lists are frozen in
``eval/splits/<dataset>.json`` and re-checked on every ``prepare``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

SPLIT_RULE = "iris-split/1"


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


def list_digest(ids: Iterable[str]) -> str:
    """sha256 over the sorted IDs, one per line; recorded beside each frozen list."""
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()
