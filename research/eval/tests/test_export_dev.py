"""export_dev: dev pages only, size estimate, import on the receiving side."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fakeserver import FakeServer, serve
from PIL import Image
from test_pack_fetch import fatura_archive, make_zip, run, with_sources

from iris_eval import export as export_mod
from iris_eval import index as index_mod
from iris_eval.export import ExportError, import_export, plan_export, write_export
from iris_eval.manifests import load_manifest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    with serve() as server:
        yield _prepare(server, tmp_path, monkeypatch)


def _prepare(server: FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    url = server.add("/FATURA2.zip", make_zip(fatura_archive(templates=6, per=10, size=2000)))
    m = with_sources("fatura", {"archive": {"url": url}}, sample_per_category=20)
    run(m, tmp_path)
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    (mdir / "fatura.json").write_text(json.dumps(m))
    loader = lambda ds: load_manifest(ds, mdir)  # noqa: E731
    monkeypatch.setattr(index_mod, "load_manifest", loader)
    monkeypatch.setattr(export_mod, "load_manifest", loader)
    monkeypatch.setenv("IRIS_EVAL_DATA", str(tmp_path / "data"))
    index_mod.prepare("fatura", splits_dir=tmp_path / "splits")
    frozen = json.loads((tmp_path / "splits" / "fatura.json").read_text())["categories"]["invoices"]
    return {"tmp": tmp_path, "dev": set(frozen["dev"]), "heldout": set(frozen["heldout"])}


def test_export_contains_dev_only(prepared: dict[str, Any]) -> None:
    tmp = prepared["tmp"]
    plan = plan_export(["fatura"], splits_dir=tmp / "splits")
    assert len(plan.items) == 12 and plan.size_bytes > 12 * 2000
    out = write_export(plan, tmp / "out" / "iris-dev.zip")
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        info = json.loads(z.read("EXPORT.json"))
        gts = [json.loads(z.read(n)) for n in names if n.startswith("gt/")]
    assert info["datasets"]["fatura"] == {"use": "allowed", "dev_pages": 12}
    ids = {g["id"].split("/", 1)[1] for g in gts}
    assert ids == prepared["dev"] and not ids & prepared["heldout"]
    assert all(g["split"] == "dev" and g["image"].startswith("images/fatura/") for g in gts)
    assert not any(h in n for n in names for h in prepared["heldout"])
    assert all("\\" not in n for n in names)


def test_export_stops_on_a_heldout_page(prepared: dict[str, Any]) -> None:
    tmp = prepared["tmp"]
    ip = tmp / "data" / "index" / "fatura.jsonl"
    lines = [json.loads(x) for x in ip.read_text().splitlines()]
    held = next(e for e in lines if e["split"] == "heldout")
    held["split"] = "dev"  # a corrupted index must not leak a held-out page
    ip.write_text("\n".join(json.dumps(e) for e in lines) + "\n")
    with pytest.raises(ExportError, match="not in the frozen dev split"):
        plan_export(["fatura"], splits_dir=tmp / "splits")


def test_eval_only_and_private_need_flags(prepared: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    tmp = prepared["tmp"]
    m = json.loads((tmp / "manifests" / "fatura.json").read_text())
    m["use"] = "evaluation-only"
    (tmp / "manifests" / "fatura.json").write_text(json.dumps(m))
    with pytest.raises(ExportError, match="accept-eval-only"):
        plan_export(["fatura"], splits_dir=tmp / "splits")
    priv = tmp / "priv" / "receipts"
    priv.mkdir(parents=True)
    Image.new("RGB", (4, 4), "white").save(priv / "p.png")
    (priv / "p.gt.json").write_text(json.dumps({"pairs": [{"key": None, "field": "total", "value": "1.00"}]}))
    seen = tmp / "seen.txt"
    seen.write_text("p.png\n")
    monkeypatch.setenv("OCR_PRIVATE_DATA", str(tmp / "priv"))
    monkeypatch.setenv("OCR_PRIVATE_SEEN", str(seen))
    plan = plan_export(["fatura"], accept_eval_only=True, include_private=True, splits_dir=tmp / "splits")
    assert plan.info["datasets"]["private"]["dev_pages"] == 1
    no_private = plan_export(["fatura"], accept_eval_only=True, splits_dir=tmp / "splits")
    assert no_private.info["datasets"].keys() == {"fatura"}


def test_import_makes_the_dev_split_usable(prepared: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    tmp = prepared["tmp"]
    out = write_export(plan_export(["fatura"], splits_dir=tmp / "splits"), tmp / "iris-dev.zip")
    dest = tmp / "sandbox-data"
    import_export(out, dest)
    monkeypatch.setenv("IRIS_EVAL_DATA", str(dest))
    entries = index_mod.load_index("fatura")
    assert len(entries) == 12 and all(e.split == "dev" for e in entries)
    assert all(Path(e.image).is_file() and e.gt_path.is_file() for e in entries)
    from iris_eval.gt import load_gt

    assert load_gt(entries[0].gt_path).split == "dev"


def test_import_refuses_unsafe_or_heldout_members(tmp_path: Path) -> None:
    def z(members: dict[str, bytes]) -> Path:
        p = tmp_path / f"x{len(list(tmp_path.iterdir()))}.zip"
        p.write_bytes(make_zip(members))
        return p

    info = json.dumps({"schema": "iris-dev-export/1", "split": "dev", "datasets": {}}).encode()
    with pytest.raises(ExportError, match="non-dev"):
        import_export(z({"EXPORT.json": info, "gt/d/heldout/a.gt.json": b"{}"}), tmp_path / "d")
    with pytest.raises(ValueError):
        import_export(z({"EXPORT.json": info, "images/../../evil.png": b"x"}), tmp_path / "d")


def _cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_dev", REPO / "eval" / "export_dev.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_dry_run_prints_estimate_and_writes_nothing(prepared: dict[str, Any],
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    tmp = prepared["tmp"]
    code = _cli().main(["--dataset", "fatura", "--data-dir", str(tmp / "data"), "--splits-dir", str(tmp / "splits"),
                        "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0 and "estimated zip size" in out and "12 dev pages" in out
    assert not (tmp / "data" / "exports").exists()
