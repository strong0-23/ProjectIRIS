"""Archive member names to safe relative paths that work on Windows, macOS and Linux.

Relative paths are always stored with ``/`` (in locks and ``pack.json``) and turned into local
paths only when a file is written or read, so a lock written on Windows verifies on Linux and the
other way round.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePath, PurePosixPath

# Windows reserves these device names in every folder, with or without an extension.
_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
# Keep relative paths short so <data dir>/raw/<dataset>/<rel> stays under Windows' 260-character
# limit for typical data folders; longer member paths are stored under a hashed name.
MAX_REL = 120


class UnsafePath(ValueError):
    pass


def safe_relpath(name: str) -> str:
    """Validate an archive member or URL path and return it as a ``/``-separated relative path.

    Refuses absolute paths, drive letters, ``..``, characters Windows cannot store, reserved
    device names and components ending in a dot or space.
    """
    norm = name.replace("\\", "/")
    if not norm or norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise UnsafePath(f"absolute or empty path: {name!r}")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts:
        raise UnsafePath(f"empty path: {name!r}")
    for p in parts:
        if p == "..":
            raise UnsafePath(f"path escapes its folder: {name!r}")
        if _BAD_CHARS.search(p):
            raise UnsafePath(f"character not allowed on Windows in {name!r}")
        if p.endswith((".", " ")):
            raise UnsafePath(f"component ends with a dot or space in {name!r}")
        if p.split(".")[0].lower() in _RESERVED:
            raise UnsafePath(f"reserved Windows name in {name!r}")
    return "/".join(parts)


def storage_rel(prefix: str, member: str) -> str:
    """Where a member is stored under ``raw/<dataset>/``: ``<prefix>/<member>``, or a hashed name
    under ``<prefix>/_long/`` when that path would be too long."""
    rel = safe_relpath(f"{prefix}/{member}")
    if len(rel) <= MAX_REL:
        return rel
    suffix = PurePosixPath(rel).suffix[:10]
    digest = hashlib.sha1(member.encode("utf-8")).hexdigest()[:24]
    return f"{safe_relpath(prefix)}/_long/{digest}{suffix}"


def local_path(root: PurePath, rel: str) -> PurePath:
    """Join a ``/``-separated relative path onto a local root of any flavour (Path, PureWindowsPath)."""
    out = root
    for p in safe_relpath(rel).split("/"):
        out = out / p
    return out


def as_path(root: Path, rel: str) -> Path:
    p = local_path(root, rel)
    assert isinstance(p, Path)
    return p
