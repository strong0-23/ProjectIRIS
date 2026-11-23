"""The private slot: the owner's own photos, outside the repository (docs/DECISIONS.md O7).

``OCR_PRIVATE_DATA`` points at one folder the owner keeps adding to::

    $OCR_PRIVATE_DATA/
      <category>/<photo>.<png|jpg|jpeg|tif|tiff|webp|heic>
      <category>/<photo stem>.gt.json       optional ground truth (or <photo file name>.gt.json)
      .iris-split.json                      frozen split assignment, written by the harness

``<category>`` is one of the IRIS categories (``gt.CATEGORIES``); other folders are reported and
skipped.

**Split rule ``iris-private/1``.** The first time the harness sees a photo it assigns it to dev
or held-out and freezes that in ``.iris-split.json`` (inside the private folder, never in the
repository):

- a photo on the *seen list* (photos agents already saw during SplitLah) is ``dev``;
- otherwise ``dev`` when ``int(sha256("iris-private/1:<sha256 of the photo bytes>")[:8], 16)
  < dev_fraction * 2**32`` (dev fraction 0.6), else ``heldout``.

The rule uses the photo's bytes only through a hash, so it cannot be steered by looking at the
photo, and it does not depend on the order photos arrive. A photo moved or renamed keeps its
assignment (matched by hash). A frozen assignment never changes, with one exception: a held-out
photo that later turns up on the seen list moves to dev (reason ``seen-after-assignment``),
because a seen photo can no longer measure unseen performance.

**Seen list.** A text file, path given at run time (``--seen-list`` or ``OCR_PRIVATE_SEEN``),
never committed: one entry per line, either the photo's sha256 or its file name / relative path
(``<category>/<file>``); ``#`` starts a comment.

**Ground truth.** ``.gt.json`` holds ``iris-gt/1`` (``id``, ``dataset``, ``category``, ``split``
and ``image`` may be left out: they come from the path and the assignment), or a SplitLah owner
reference (see ``splitlah_to_gt`` and eval/README.md), converted to key-value ground truth.

Results carry only the page ID and numbers, never text. Nothing from these photos is committed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gt import CATEGORIES, GT_SCHEMA, SPLITS, parse_gt
from .index import IndexEntry
from .paths import PRIVATE_ENV, safe_key

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".heic")
ASSIGN_FILE = ".iris-split.json"
ASSIGN_SCHEMA = "iris-private-split/1"
PRIVATE_RULE = "iris-private/1"
DEV_FRACTION = 0.6
SEEN_ENV = "OCR_PRIVATE_SEEN"
SPLITLAH_SCHEMA = "splitlah-ref/1"


class PrivateDataError(RuntimeError):
    pass


def private_root() -> Path | None:
    v = os.environ.get(PRIVATE_ENV)
    return Path(v).resolve() if v else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rule_split(photo_sha256: str, dev_fraction: float = DEV_FRACTION) -> str:
    """``iris-private/1`` for a photo that is not on the seen list."""
    h = hashlib.sha256(f"{PRIVATE_RULE}:{photo_sha256}".encode()).hexdigest()
    return "dev" if int(h[:8], 16) < dev_fraction * 2**32 else "heldout"


@dataclass(frozen=True)
class Photo:
    rel: str  # "<category>/<file name>", always with "/"
    path: Path
    category: str


@dataclass
class SeenList:
    hashes: set[str]
    names: set[str]  # lower-case file names and relative paths

    def __contains__(self, item: tuple[str, str]) -> bool:
        rel, sha = item
        return sha in self.hashes or rel.lower() in self.names or rel.rsplit("/", 1)[-1].lower() in self.names

    @classmethod
    def empty(cls) -> SeenList:
        return cls(set(), set())


def load_seen(path: Path | None) -> SeenList:
    if path is None:
        env = os.environ.get(SEEN_ENV)
        path = Path(env) if env else None
    if path is None:
        return SeenList.empty()
    if not path.is_file():
        raise PrivateDataError(f"seen list {path} not found")
    seen = SeenList.empty()
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        entry = raw.split("#", 1)[0].strip()
        if not entry:
            continue
        low = entry.lower().replace("\\", "/")
        if len(low) == 64 and all(c in "0123456789abcdef" for c in low):
            seen.hashes.add(low)
        else:
            seen.names.add(low)
    return seen


def scan(root: Path) -> tuple[list[Photo], list[str]]:
    """Photos under ``root/<category>/``, and the names of folders that are not categories."""
    if (root / "dev").is_dir() or (root / "heldout").is_dir():
        raise PrivateDataError(
            f"{root} uses the old dev/ and heldout/ layout (WO-001). Move each photo to {root}/<category>/; "
            "the split is now assigned by rule and frozen (O7)."
        )
    photos: list[Photo] = []
    skipped: list[str] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if d.name not in CATEGORIES:
            skipped.append(d.name)
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES and not f.name.startswith("."):
                photos.append(Photo(f"{d.name}/{f.name}", f, d.name))
    return photos, skipped


def _read_assignments(root: Path) -> dict[str, Any]:
    p = root / ASSIGN_FILE
    if not p.is_file():
        return {"schema": ASSIGN_SCHEMA, "rule": PRIVATE_RULE, "dev_fraction": DEV_FRACTION, "photos": {}}
    with p.open(encoding="utf-8") as f:
        d: dict[str, Any] = json.load(f)
    if d.get("schema") != ASSIGN_SCHEMA:
        raise PrivateDataError(f"{p} is not an {ASSIGN_SCHEMA} file")
    return d


def sync_assignments(root: Path, seen: SeenList | None = None, today: str | None = None) -> dict[str, Any]:
    """Assign every photo not seen before, apply the seen list, and write the frozen file.

    Returns the assignment record: ``photos[<category>/<file>] = {sha256, split, reason, first_seen}``.
    """
    seen = seen or SeenList.empty()
    today = today or _dt.date.today().isoformat()
    rec = _read_assignments(root)
    frac = float(rec.get("dev_fraction", DEV_FRACTION))
    known: dict[str, dict[str, Any]] = rec["photos"]
    by_hash = {v["sha256"]: v for v in known.values()}
    changed = False
    photos, _ = scan(root)
    for ph in photos:
        entry = known.get(ph.rel)
        sha = _sha256(ph.path)
        if entry is None:
            prev = by_hash.get(sha)
            if prev is not None:  # moved or renamed (or a copy): keep the frozen split
                entry = {**prev, "first_seen": prev.get("first_seen", today)}
            elif (ph.rel, sha) in seen:
                entry = {"sha256": sha, "split": "dev", "reason": "seen", "first_seen": today}
            else:
                entry = {"sha256": sha, "split": rule_split(sha, frac), "reason": "rule", "first_seen": today}
            known[ph.rel] = entry
            by_hash.setdefault(sha, entry)
            changed = True
        elif entry["sha256"] != sha and not entry.get("content_changed"):
            entry["content_changed"] = today  # edited in place: the frozen split stays
            changed = True
        if entry["split"] == "heldout" and (ph.rel, entry["sha256"]) in seen:
            entry.update(split="dev", reason="seen-after-assignment", moved=today)
            changed = True
    if changed or not (root / ASSIGN_FILE).is_file():
        rec["photos"] = dict(sorted(known.items()))
        tmp = root / (ASSIGN_FILE + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(rec, f, indent=1)
            f.write("\n")
        tmp.replace(root / ASSIGN_FILE)
    return rec


def _gt_file(ph: Photo) -> Path | None:
    for cand in (ph.path.with_name(ph.path.stem + ".gt.json"), ph.path.with_name(ph.path.name + ".gt.json")):
        if cand.is_file():
            return cand
    return None


def load_private(split: str, root: Path | None = None, seen: SeenList | None = None) -> list[IndexEntry]:
    """Index the private photos of one split that have ground truth (assigning new photos first)."""
    if split not in SPLITS:
        raise ValueError(split)
    root = root or private_root()
    if root is None or not root.is_dir():
        return []
    rec = sync_assignments(root, seen if seen is not None else load_seen(None))
    out: list[IndexEntry] = []
    for ph in scan(root)[0]:
        a = rec["photos"].get(ph.rel)
        gt = _gt_file(ph)
        if a is None or a["split"] != split or gt is None:
            continue
        stem = ph.path.stem
        out.append(IndexEntry(id=f"private/{ph.category}/{stem}", key=safe_key(f"{ph.category}__{stem}"),
                              dataset="private", category=ph.category, split=split, gt_path=gt,
                              image=str(ph.path), private=True))
    ids = [e.id for e in out]
    if len(set(ids)) != len(ids):
        raise PrivateDataError("two private photos in one category share a file stem; rename one")
    return out


def status(root: Path, seen: SeenList | None = None) -> dict[str, Any]:
    """Counts per category and split (no file names), for the owner's console."""
    rec = sync_assignments(root, seen)
    photos, skipped = scan(root)
    counts: dict[str, dict[str, int]] = {}
    for ph in photos:
        a = rec["photos"][ph.rel]
        c = counts.setdefault(ph.category, {"dev": 0, "heldout": 0, "with_gt": 0, "seen": 0})
        c[a["split"]] += 1
        c["with_gt"] += _gt_file(ph) is not None
        c["seen"] += a["reason"].startswith("seen")
    return {"categories": counts, "skipped_folders": len(skipped), "rule": PRIVATE_RULE}


# ------------------------------------------------------------------ ground truth


def _cents(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    s = str(v).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    raise PrivateDataError(f"amount {v!r} is not an integer number of cents")


def money(cents: int) -> str:
    """Integer cents as the canonical printed amount: ``1070 -> "10.70"``, ``-100 -> "-1.00"``."""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


CHARGE_FIELDS = {"service": "service_charge", "service_charge": "service_charge", "svc": "service_charge",
                 "gst": "gst", "tax": "tax", "vat": "tax", "discount": "discount", "rounding": "rounding",
                 "subtotal": "subtotal"}


def is_splitlah(d: dict[str, Any]) -> bool:
    return d.get("schema") == SPLITLAH_SCHEMA or (
        d.get("schema") is None and "items" in d and not any(k in d for k in ("text", "tables", "pairs")))


def splitlah_to_gt(ref: dict[str, Any]) -> dict[str, Any]:
    """Convert a SplitLah owner reference to ``iris-gt/1`` key-value ground truth (no text).

    Every field except ``items`` is optional. Amounts are integer cents; they become canonical
    two-decimal strings (``money``). Pairs: ``merchant``; per item ``item_name``, ``item_quantity``
    (only when given) and ``item_amount`` (key = item name); one pair per non-zero charge
    (``service_charge``, ``gst``, ``tax``, ``discount``, ``rounding``, ``subtotal``); ``total``.
    """
    pairs: list[dict[str, Any]] = []
    merchant = _first(ref, "merchant", "store", "shop")
    if isinstance(merchant, dict):
        merchant = _first(merchant, "name", "merchant")
    if merchant:
        pairs.append({"key": None, "field": "merchant", "value": " ".join(str(merchant).split())})
    for it in ref.get("items") or []:
        if not isinstance(it, dict):
            raise PrivateDataError("each item must be an object")
        name = _first(it, "name", "description", "item")
        name = " ".join(str(name).split()) if name else None
        if name:
            pairs.append({"key": None, "field": "item_name", "value": name})
        qty = _first(it, "quantity", "qty")
        if qty is not None:
            pairs.append({"key": name, "field": "item_quantity", "value": str(qty)})
        amount = _cents(_first(it, "amount", "amount_cents", "total_cents", "line_total"))
        if amount is not None:
            pairs.append({"key": name, "field": "item_amount", "value": money(amount)})
    charges = ref.get("charges") or {}
    items: list[tuple[str, Any]] = []
    if isinstance(charges, dict):
        items = list(charges.items())
    elif isinstance(charges, list):
        items = [(str(_first(c, "type", "kind", "name") or ""), _first(c, "amount", "amount_cents")) for c in charges
                 if isinstance(c, dict)]
    for kind, amount in items:
        field = CHARGE_FIELDS.get(str(kind).strip().lower().replace(" ", "_"))
        cents = _cents(amount)
        if field and cents:
            pairs.append({"key": None, "field": field, "value": money(cents)})
    total = _cents(_first(ref, "total", "printed_total", "total_cents", "printedTotal"))
    if total is not None:
        pairs.append({"key": None, "field": "total", "value": money(total)})
    if not pairs:
        raise PrivateDataError("SplitLah reference has no items, charges or total")
    return {"schema": GT_SCHEMA, "conditions": list(ref.get("conditions") or []), "text": None, "tables": None,
            "pairs": pairs, "source_attributes": {"format": SPLITLAH_SCHEMA, "currency": ref.get("currency")}}


def read_private_gt(entry: IndexEntry) -> dict[str, object]:
    with entry.gt_path.open(encoding="utf-8") as f:
        d = json.load(f)
    if is_splitlah(d):
        d = splitlah_to_gt(d)
    d.setdefault("schema", GT_SCHEMA)
    d["id"] = entry.id
    d["dataset"] = "private"
    d["category"] = entry.category
    d["split"] = entry.split
    d["image"] = entry.image
    parse_gt(d)
    return dict(d)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Private slot: split status and SplitLah conversion (counts only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="assign new photos and print counts per category and split")
    st.add_argument("--seen-list", type=Path)
    cv = sub.add_parser("convert-splitlah", help="convert a SplitLah reference JSON to iris-gt/1")
    cv.add_argument("ref", type=Path)
    cv.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "status":
            root = private_root()
            if root is None:
                print(f"{PRIVATE_ENV} is not set", file=sys.stderr)
                return 2
            print(json.dumps(status(root, load_seen(a.seen_list)), indent=1))
            return 0
        with a.ref.open(encoding="utf-8") as f:
            gt = splitlah_to_gt(json.load(f))
        with a.out.open("w", encoding="utf-8") as f:
            json.dump(gt, f, indent=1, ensure_ascii=False)
        print(f"wrote {len(gt['pairs'])} pairs")
        return 0
    except (PrivateDataError, OSError, ValueError) as exc:
        print(f"private: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
