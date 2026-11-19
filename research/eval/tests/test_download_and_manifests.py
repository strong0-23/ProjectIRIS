import hashlib
import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

from iris_eval.manifests import ManifestError, list_manifests, validate_manifest

REPO = Path(__file__).resolve().parents[3]


def _download_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("iris_download", REPO / "eval" / "download.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dl = _download_module()


def _manifest(url: str, sha: str | None, use: str = "allowed", unpack: str | None = None) -> dict:
    return {"id": "toy", "use": use, "use_reason": "test",
            "files": [{"url": url, "dest": "data.zip", "sha256": sha, "bytes": None, "unpack": unpack}]}


def _zip(path: Path, members: dict[str, str]) -> str:
    with zipfile.ZipFile(path, "w") as z:
        for name, content in members.items():
            z.writestr(name, content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fetch_verify_unpack(tmp_path: Path) -> None:
    src = tmp_path / "src.zip"
    sha = _zip(src, {"dir/a.txt": "hello"})
    root = tmp_path / "data"
    dl.download(_manifest(src.as_uri(), sha, unpack="zip"), root, False, False)
    assert (root / "raw/toy/unpacked/data.zip/dir/a.txt").read_text() == "hello"
    dl.download(_manifest(src.as_uri(), sha, unpack="zip"), root, False, False)  # idempotent


def test_bad_checksum_is_rejected(tmp_path: Path) -> None:
    src = tmp_path / "src.zip"
    _zip(src, {"a.txt": "x"})
    with pytest.raises(dl.DownloadError, match="checksum failed"):
        dl.download(_manifest(src.as_uri(), "0" * 64), tmp_path / "d", False, False)


def test_licence_gate_and_unpinned(tmp_path: Path) -> None:
    src = tmp_path / "src.zip"
    sha = _zip(src, {"a.txt": "x"})
    with pytest.raises(dl.DownloadError, match="excluded"):
        dl.download(_manifest(src.as_uri(), sha, use="excluded"), tmp_path / "d", True, True)
    with pytest.raises(dl.DownloadError, match="accept-eval-only"):
        dl.download(_manifest(src.as_uri(), sha, use="evaluation-only-needs-decision"), tmp_path / "d", False, False)
    with pytest.raises(dl.DownloadError, match="no pinned checksum"):
        dl.download(_manifest(src.as_uri(), None), tmp_path / "d", False, False)
    dl.download(_manifest(src.as_uri(), None), tmp_path / "d", False, True)


def test_path_traversal_is_refused(tmp_path: Path) -> None:
    src = tmp_path / "evil.zip"
    sha = _zip(src, {"../escape.txt": "x"})
    with pytest.raises(dl.DownloadError, match="escapes"):
        dl.download(_manifest(src.as_uri(), sha, unpack="zip"), tmp_path / "d", False, False)
    assert not (tmp_path / "d" / "raw" / "escape.txt").exists()


def test_unreachable_host_is_reported(tmp_path: Path) -> None:
    with pytest.raises(dl.DownloadError, match="not reachable"):
        dl.fetch((tmp_path / "missing.zip").as_uri(), tmp_path / "out.zip")


def test_every_repo_manifest_is_valid_and_licensed() -> None:
    ms = list_manifests()
    assert len(ms) >= 10
    cats = set()
    for m in ms:
        assert m["licence"]["url"].startswith("http")
        if m["use"] != "allowed":
            assert m.get("use_reason")
        if m["use"] == "allowed":
            assert m["commercial_use"] is True
        cats.update(m["categories"])
    assert {"receipts", "invoices", "forms", "letters-and-reports", "tables",
            "book-or-scanned-pages", "phone-photos-hard"} <= cats


def test_manifest_validation_rejects_bad_dest() -> None:
    m = list_manifests()[0]
    bad = {**m, "files": [{"url": "https://x", "dest": "../x"}]}
    with pytest.raises(ManifestError):
        validate_manifest(bad)
