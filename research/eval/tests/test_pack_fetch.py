"""fetch_pack: sample-only download, locks, gates, fallbacks and planners, against a local fake
server and fake archives (no real dataset content)."""

from __future__ import annotations

import copy
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pytest
from fakeserver import FakeServer, serve

from iris_eval import index as index_mod
from iris_eval.manifests import ManifestError, load_manifest, validate_manifest
from iris_eval.pack.fetch import PackRefused, PackSkipped, fetch_dataset, summary
from iris_eval.pack.lock import Lock, LockError
from iris_eval.pack.remote import FetchError, RemoteFile
from iris_eval.pack.safepath import MAX_REL, UnsafePath, local_path, safe_relpath, storage_rel

REPO = Path(__file__).resolve().parents[3]


def fake_bytes(seed: str, n: int) -> bytes:
    """Incompressible filler (not real data)."""
    import hashlib

    out = bytearray()
    i = 0
    while len(out) < n:
        out += hashlib.sha256(f"{seed}:{i}".encode()).digest()
        i += 1
    return bytes(out[:n])


def make_zip(members: dict[str, bytes], compress: int = zipfile.ZIP_STORED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compress) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def with_sources(dataset: str, urls: dict[str, dict[str, Any]], **split: Any) -> dict[str, Any]:
    """The repo manifest of ``dataset`` with its pack sources pointed at the fake server."""
    m = copy.deepcopy(load_manifest(dataset))
    for s in m["pack"]["sources"]:
        s.update(urls.get(s["name"], {}))
        for pin in ("sha256", "md5", "bytes"):
            if pin not in urls.get(s["name"], {}):
                s.pop(pin, None)
    m["split"].update(split)
    return validate_manifest(m)


def run(m: dict[str, Any], tmp: Path, **kw: Any) -> Any:
    return fetch_dataset(m, data_root=tmp / "data", lock_dir=tmp / "locks", splits_dir=tmp / "splits",
                         log=lambda s: None, **kw)


@pytest.fixture
def server() -> Any:
    with serve() as s:
        yield s


# ------------------------------------------------------------------ paths (Windows rules)


def test_safe_relpath_normalises_and_refuses_unsafe_names() -> None:
    assert safe_relpath("a\\b\\c.png") == "a/b/c.png"
    assert safe_relpath("./a//b.png") == "a/b.png"
    for bad in ("../x", "a/../../x", "/abs/x", "C:\\x\\y", "c:/x", "a/CON.txt", "a/aux", "a/b:c.png",
                "a/b?.png", "a/trailing.", "a/space ", "", "a/\x01.png"):
        with pytest.raises(UnsafePath):
            safe_relpath(bad)


def test_local_paths_on_a_windows_data_dir() -> None:
    root = PureWindowsPath(r"C:\Users\Owner\Project IRIS\eval\.data\raw\fatura")
    p = local_path(root, "archive/invoices_dataset_final/images/Template1_Instance0.jpg")
    assert str(p) == (r"C:\Users\Owner\Project IRIS\eval\.data\raw\fatura\archive"
                      r"\invoices_dataset_final\images\Template1_Instance0.jpg")
    assert isinstance(local_path(PurePosixPath("/data"), "a/b"), PurePosixPath)
    long = "x" * 200 + "/photo.jpg"
    rel = storage_rel("archive", long)
    assert len(rel) <= MAX_REL and rel.startswith("archive/_long/") and rel.endswith(".jpg")
    assert storage_rel("archive", long) == rel  # deterministic
    # Lock keys are "/"-separated whatever the OS; a path given with backslashes maps to the same key.
    assert storage_rel("core", "PNG\\abc.png") == storage_rel("core", "PNG/abc.png") == "core/PNG/abc.png"
    total = len(str(PureWindowsPath(r"C:\Users\Owner\Documents\ProjectIRIS\eval\.data\raw\smartdoc2015-ch2")
                    / PureWindowsPath(rel)))
    assert total < 260


# ------------------------------------------------------------------ remote zip by range


def test_remote_zip_reads_one_member_with_few_bytes(server: FakeServer) -> None:
    members = {f"PNG/p{i:03d}.png": fake_bytes(f"p{i}", 200_000) for i in range(40)}
    data = make_zip(members)
    url = server.add("/big.zip", data)
    rf = RemoteFile(url)
    z = zipfile.ZipFile(rf)  # type: ignore[arg-type]
    info = z.getinfo("PNG/p007.png")
    rf.prefetch(info.header_offset, 30 + len(info.filename) + 1024 + info.compress_size)
    assert z.read(info) == members["PNG/p007.png"]
    assert rf.bytes_fetched < len(data) / 10
    assert rf.size == len(data)


def test_server_without_range_is_detected(server: FakeServer) -> None:
    url = server.add("/plain.zip", make_zip({"a.txt": b"x"}), ranges=False)
    with pytest.raises(FetchError, match="range"):
        RemoteFile(url)


# ------------------------------------------------------------------ an end-to-end pack (FATURA-like, grouped)


def fatura_archive(templates: int = 10, per: int = 20, size: int = 30_000) -> dict[str, bytes]:
    out: dict[str, bytes] = {"invoices_dataset_final/README.txt": b"synthetic test archive"}
    for t in range(1, templates + 1):
        for i in range(per):
            pid = f"Template{t}_Instance{i}"
            out[f"invoices_dataset_final/images/{pid}.jpg"] = fake_bytes(pid, size)
            out[f"invoices_dataset_final/colored_images/{pid}.jpg"] = fake_bytes(pid + "c", size)
            out[f"invoices_dataset_final/Annotations/Original_Format/{pid}.json"] = json.dumps(
                {"TOTAL": {"bbox": [0, 0, 1, 1], "text": f"Total: {t}.{i:02d} EUR"},
                 "NOTE": {"bbox": [0, 0, 1, 1], "text": "Synthetic note\nline two"}}).encode()
    return out


def test_fatura_pack_end_to_end(server: FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = make_zip(fatura_archive())
    url = server.add("/FATURA2.zip", data)
    m = with_sources("fatura", {"archive": {"url": url}}, sample_per_category=20)
    r = run(m, tmp_path)
    assert r.counts == {"invoices": {"available": 200, "dev": 12, "heldout": 8}}
    assert r.split_status == "frozen split written" and r.lock_status == "lock written"
    assert r.downloaded_bytes < len(data) / 5  # 20 pages of 200, plus the directory
    raw = tmp_path / "data" / "raw" / "fatura"
    pack = json.loads((raw / "pack.json").read_text())
    images = list((raw / "archive").rglob("*.jpg"))
    assert len(images) == 20 and not list((raw / "archive").rglob("colored_images"))
    frozen = json.loads((tmp_path / "splits" / "fatura.json").read_text())
    groups = {p["id"]: p["group"] for p in pack["population"]}
    dev_g = {groups[i] for i in frozen["categories"]["invoices"]["dev"]}
    held_g = {groups[i] for i in frozen["categories"]["invoices"]["heldout"]}
    assert dev_g and held_g and not dev_g & held_g  # no template on both sides
    lock = json.loads((tmp_path / "locks" / "fatura.lock.json").read_text())
    assert lock["complete"] and len(lock["files"]) == 40 and lock["sources"]["archive"]["bytes"] == len(data)
    assert all(set(e) == {"bytes", "sha256"} for e in lock["files"].values())

    # Second run: everything verified against the lock, only the directory is read again.
    r2 = run(m, tmp_path)
    assert r2.split_status == "matches frozen split" and r2.lock_status == "verified against lock"
    assert r2.fetched_files == 0 and r2.reused_files == 40

    # A damaged local file is fetched again and must match the lock.
    images[0].write_bytes(b"damaged")
    r3 = run(m, tmp_path)
    assert r3.fetched_files == 1 and images[0].stat().st_size == 30_000

    # prepare (converter) reproduces the frozen split from pack.json and writes valid iris-gt/1.
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    (mdir / "fatura.json").write_text(json.dumps(m))
    monkeypatch.setattr(index_mod, "load_manifest", lambda ds: load_manifest(ds, mdir))
    monkeypatch.setenv("IRIS_EVAL_DATA", str(tmp_path / "data"))
    s = index_mod.prepare("fatura", splits_dir=tmp_path / "splits")
    assert s["split_status"] == "matches frozen split" and s["counts"]["invoices"] == {"dev": 12, "heldout": 8}
    entries = index_mod.load_index("fatura")
    gt = json.loads(entries[0].gt_path.read_text())
    assert gt["schema"] == "iris-gt/1" and gt["pairs"][0]["field"] == "total" and gt["pairs"][0]["key"] == "Total"
    assert "Synthetic note" in gt["text"]["lines"]


def test_remote_archive_change_is_refused(server: FakeServer, tmp_path: Path) -> None:
    url = server.add("/FATURA2.zip", make_zip(fatura_archive(templates=4, per=5, size=1000)))
    m = with_sources("fatura", {"archive": {"url": url}}, sample_per_category=10)
    run(m, tmp_path)
    server.files["/FATURA2.zip"] = make_zip(fatura_archive(templates=4, per=5, size=1001))
    with pytest.raises(LockError, match="changed since the lock"):
        run(m, tmp_path)


def test_no_range_falls_back_to_whole_only_under_the_cap(server: FakeServer, tmp_path: Path) -> None:
    data = make_zip(fatura_archive(templates=4, per=5, size=1000))
    url = server.add("/FATURA2.zip", data, ranges=False)
    m = with_sources("fatura", {"archive": {"url": url, "whole_max_bytes": len(data)}}, sample_per_category=10)
    with pytest.raises(FetchError, match="over the limit"):
        run(m, tmp_path / "a", max_whole_bytes=len(data) - 1)
    r = run(m, tmp_path / "b", max_whole_bytes=10**9)
    assert r.downloaded_bytes == len(data)
    assert (tmp_path / "b" / "data" / "raw" / "fatura" / "FATURA2.zip").stat().st_size == len(data)
    assert r.counts["invoices"]["dev"] == 6


def test_licence_gate(tmp_path: Path) -> None:
    for ds, flag, msg in (("sroie", True, "excluded"), ("funsd", False, "accept-eval-only"),
                          ("olmocr-bench", True, "no data pack")):
        with pytest.raises(PackRefused, match=msg):
            run(load_manifest(ds), tmp_path, accept_eval_only=flag)
    m = copy.deepcopy(load_manifest("funsd"))
    m["use"] = "evaluation-only-needs-decision"
    with pytest.raises(PackRefused, match="without an owner decision"):
        run(m, tmp_path, accept_eval_only=True)


def test_lock_refuses_new_files_once_complete(tmp_path: Path) -> None:
    lk = Lock(tmp_path / "x.lock.json", "x")
    lk.record("a/b.png", 3, "0" * 64)
    lk.save(complete=True)
    lk2 = Lock(tmp_path / "x.lock.json", "x")
    with pytest.raises(LockError, match="update-lock"):
        lk2.record("a/c.png", 3, "1" * 64)
    with pytest.raises(LockError, match="does not match"):
        lk2.record("a/b.png", 4, "0" * 64)
    Lock(tmp_path / "x.lock.json", "x", update=True).record("a/c.png", 3, "1" * 64)


# ------------------------------------------------------------------ planners of the other datasets


def test_doclaynet_pack(server: FakeServer, tmp_path: Path) -> None:
    hashes = [f"{i:064x}" for i in range(1, 31)]
    images = [{"id": n, "file_name": f"{h}.png", "doc_category": "manuals", "precedence": 0}
              for n, h in enumerate(hashes)]
    images.append({"id": 99, "file_name": f"{hashes[0]}.png", "precedence": 1})  # redundant annotation
    core = {"DocLayNet_core/COCO/test.json": json.dumps({"images": images, "annotations": []}).encode(),
            "DocLayNet_core/COCO/train.json": b"{}"}
    core |= {f"DocLayNet_core/PNG/{h}.png": fake_bytes(h, 5000) for h in hashes}
    extra = {f"DocLayNet_extra/JSON/{h}.json": json.dumps({"cells": [
        {"bbox": [10, 20, 5, 5], "text": "second"}, {"bbox": [10, 5, 5, 5], "text": "first"}]}).encode()
        for h in hashes}
    extra |= {f"DocLayNet_extra/PDF/{h}.pdf": fake_bytes(h + "pdf", 5000) for h in hashes}
    m = with_sources("doclaynet", {"core": {"url": server.add("/core.zip", make_zip(core))},
                                   "extra": {"url": server.add("/extra.zip", make_zip(extra))}},
                     sample_per_category=10)
    r = run(m, tmp_path)
    assert r.counts["letters-and-reports"] == {"available": 30, "dev": 6, "heldout": 4}
    raw = tmp_path / "data" / "raw" / "doclaynet"
    assert len(list(raw.rglob("*.png"))) == 10 and not list(raw.rglob("*.pdf"))
    from iris_eval.datasets.doclaynet import DocLayNet

    frozen = json.loads((tmp_path / "splits" / "doclaynet.json").read_text())
    pid = frozen["categories"]["letters-and-reports"]["dev"][0]
    gt = DocLayNet().convert(raw, pid)
    assert gt["text"]["lines"] == ["first", "second"] and gt["source_attributes"]["doc_category"] == "manuals"


def smartdoc_archive(docs: int, per: int) -> dict[str, bytes]:
    out = {}
    for d in range(docs):
        for k in range(per):
            stem = f"img_{d:02d}_{k:03d}"
            out[f"testDataset/input/{stem}.jpg"] = fake_bytes(stem, 2000)
            out[f"testDataset/groundtruth/{stem}.txt"] = f"Synthetic document {d}\nline two\n".encode()
    return out


def test_smartdoc_groups_captures_by_ground_truth(server: FakeServer, tmp_path: Path) -> None:
    url = server.add("/test.zip", make_zip(smartdoc_archive(10, 12)))
    m = with_sources("smartdoc2015-ch2", {"archive": {"url": url}}, sample_per_category=20)
    m["pack"]["expected_groups"] = 10
    r = run(m, tmp_path)
    assert r.counts["phone-photos-hard"]["available"] == 120
    assert r.groups["phone-photos-hard"]["dev"] + r.groups["phone-photos-hard"]["heldout"] <= 10
    pack = json.loads((tmp_path / "data/raw/smartdoc2015-ch2/pack.json").read_text())
    rec = json.loads((tmp_path / "splits/smartdoc2015-ch2.json").read_text())["categories"]["phone-photos-hard"]
    g = {p["id"]: p["group"] for p in pack["population"]}
    assert not {g[i] for i in rec["dev"]} & {g[i] for i in rec["heldout"]}
    assert {g[i] for i in rec["dev"]} == {g[i] for i in rec["dev"] if i.startswith("img_")}
    m["pack"]["expected_groups"] = 35
    with pytest.raises(FetchError, match="expected 35"):
        run(m, tmp_path / "again")


TEST_PASSWORD = "synthetic-test-password"  # not the publisher's password


def _zipcrypto(path: Path, members: dict[str, bytes], password: str) -> None:
    work = path.parent / "zipwork"
    for name, data in members.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_bytes(data)
    subprocess.run(["zip", "-q", "-r", "-P", password, str(path), "."], cwd=work, check=True)
    shutil.rmtree(work)


@pytest.mark.skipif(shutil.which("zip") is None, reason="needs the zip program to build a ZipCrypto archive")
def test_bln600_password_archive_via_figshare_api(server: FakeServer, tmp_path: Path) -> None:
    members = {}
    for i in range(12):
        gid = f"BA{3200000000 + i}"
        members[f"BLN600/Images/{gid}.{'tif' if i % 2 else 'jpg'}"] = fake_bytes(gid, 3000)
        members[f"BLN600/Ground Truth/{gid}.txt"] = f"Synthetic article {i}\nsecond line\n".encode()
        members[f"BLN600/OCR Text/{gid}.txt"] = b"machine ocr"
    zp = tmp_path / "BLN600.zip"
    _zipcrypto(zp, members, TEST_PASSWORD)
    url = server.add("/files/123", zp.read_bytes())
    api = {"version": 2, "files": [{"id": 123, "name": "BLN600.zip", "size": zp.stat().st_size,
                                    "computed_md5": "x", "download_url": url}]}
    server.add("/api/articles/25439023", json.dumps(api).encode())
    m = with_sources("bln600", {"archive": {"api": server.url("/api")}}, sample_per_category=10)
    with pytest.raises(FetchError, match="could not read member"):  # wrong password: stops, never silent
        run(m, tmp_path / "wrong", accept_eval_only=True, passwords={"bln600": "not-it"})
    r = run(m, tmp_path / "run", accept_eval_only=True, passwords={"bln600": TEST_PASSWORD})
    assert r.counts["book-or-scanned-pages"] == {"available": 12, "dev": 6, "heldout": 4}
    lock = json.loads((tmp_path / "run/locks/bln600.lock.json").read_text())
    assert lock["sources"]["archive"]["figshare_file_id"] == 123
    from iris_eval.datasets.bln600 import Bln600

    raw = tmp_path / "run/data/raw/bln600"
    pid = json.loads((raw / "pack.json").read_text())["population"][0]["id"]
    files = json.loads((raw / "pack.json").read_text())["files"]
    some = next(iter(files))
    gt = Bln600().convert(raw, some)
    assert gt["text"]["reading_order"] and gt["text"]["lines"][1] == "second line"
    assert pid.startswith("BA")
    assert not list(raw.rglob("OCR Text"))


def test_missing_archive_password_skips_with_a_pointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IRIS_BLN600_PASSWORD", raising=False)
    m = load_manifest("bln600")
    assert "password" not in m["pack"]["sources"][0]
    with pytest.raises(PackSkipped) as exc:  # raised before any network access
        run(m, tmp_path, accept_eval_only=True)
    msg = str(exc.value)
    assert "\n" not in msg and m["homepage"] in msg and "--archive-password bln600=" in msg
    assert "IRIS_BLN600_PASSWORD" in msg and not (tmp_path / "locks").exists()
    bad = copy.deepcopy(m)
    bad["pack"]["sources"][0]["password"] = "x"
    with pytest.raises(ManifestError, match="never store"):
        validate_manifest(bad)


def test_archive_password_from_the_environment(server: FakeServer, tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    members = {"BLN600/Images/BA1.jpg": b"img", "BLN600/Ground Truth/BA1.txt": b"line\n",
               "BLN600/Images/BA2.jpg": b"img2", "BLN600/Ground Truth/BA2.txt": b"line\n"}
    if shutil.which("zip") is None:
        pytest.skip("needs the zip program")
    zp = tmp_path / "a.zip"
    _zipcrypto(zp, members, TEST_PASSWORD)
    url = server.add("/files/5", zp.read_bytes())
    files = [{"id": 5, "name": "BLN600.zip", "size": zp.stat().st_size, "download_url": url}]
    server.add("/api/articles/25439023", json.dumps({"files": files}).encode())
    monkeypatch.setenv("IRIS_BLN600_PASSWORD", TEST_PASSWORD)
    m = with_sources("bln600", {"archive": {"api": server.url("/api")}}, sample_per_category=2)
    assert run(m, tmp_path / "run", accept_eval_only=True).counts["book-or-scanned-pages"]["available"] == 2


def test_figshare_needs_exactly_one_matching_file(server: FakeServer, tmp_path: Path) -> None:
    api = {"files": [{"id": 1, "name": "a.zip", "size": 1, "download_url": "x"},
                     {"id": 2, "name": "b.zip", "size": 1, "download_url": "y"}]}
    server.add("/api/articles/25439023", json.dumps(api).encode())
    m = with_sources("bln600", {"archive": {"api": server.url("/api")}})
    with pytest.raises(FetchError, match="need exactly 1"):
        run(m, tmp_path, accept_eval_only=True, passwords={"bln600": TEST_PASSWORD})


def test_omnidocbench_per_file_pack(server: FakeServer, tmp_path: Path) -> None:
    pages = []
    for i, (src, lang) in enumerate([("book", "english")] * 6 + [("PPT2PDF", "english")] * 5 +
                                    [("note", "english")] * 3 + [("book", "simplified_chinese")] * 4):
        name = f"page_{i:02d}.jpg"
        server.add(f"/images/{name}", fake_bytes(name, 1000))
        pages.append({"page_info": {"image_path": name, "page_attribute": {"data_source": src, "language": lang}},
                      "layout_dets": [{"category_type": "text_block", "order": 0, "text": f"Synthetic {i}"}]})
    gt_url = server.add("/OmniDocBench.json", json.dumps(pages).encode())
    m = with_sources("omnidocbench", {"gt": {"url": gt_url}, "images": {"base_url": server.url("/images")}},
                     sample_per_category=5)
    r = run(m, tmp_path, accept_eval_only=True)
    assert r.counts == {"book-or-scanned-pages": {"available": 6, "dev": 3, "heldout": 2},
                        "screenshots": {"available": 5, "dev": 3, "heldout": 2}}
    fetched = [p for p, _ in server.requests if p.startswith("/images/")]
    assert len(fetched) == 10 and not any(p.endswith(("12.jpg", "13.jpg")) for p in fetched)


def test_cord_parquet_pack_and_converter(server: FakeServer, tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    from iris_eval.datasets.cord_v2 import CordV2

    def shard(n: int) -> bytes:
        def word(text: str, row: int, x: int, y: int) -> dict[str, Any]:
            return {"text": text, "row_id": row, "quad": {"x1": x, "y1": y, "y3": y + 4}}

        gts = [json.dumps({"gt_parse": {"menu": [{"nm": f"ITEM {i}", "cnt": "1", "price": "10,000"}],
                                        "total": {"total_price": "10,000"}},
                           "valid_line": [{"words": [word("ITEM", 1, 0, 5), word(f"{i}", 1, 9, 5)]},
                                          {"words": [word("TOTAL", 2, 0, 20)]}]})
               for i in range(n)]
        imgs = [{"bytes": b"\xff\xd8\xff" + fake_bytes(str(i), 50), "path": None} for i in range(n)]
        buf = io.BytesIO()
        pq.write_table(pa.table({"image": imgs, "ground_truth": gts}), buf)
        return buf.getvalue()

    m = with_sources("cord-v2", {"test": {"url": server.add("/test.parquet", shard(10))},
                                 "validation": {"url": server.add("/val.parquet", shard(10))}},
                     sample_per_category=10)
    m["pack"]["rows"] = {"test": 10, "validation": 10}
    r = run(m, tmp_path)
    assert r.counts["receipts"] == {"available": 20, "dev": 6, "heldout": 4}
    raw = tmp_path / "data/raw/cord-v2"
    gt = CordV2().convert(raw, "test/003")
    assert gt["text"]["lines"] == ["ITEM 3", "TOTAL"]
    assert {"key": "ITEM 3", "field": "item_amount", "value": "10,000"} in gt["pairs"]
    assert {"key": None, "field": "total", "value": "10,000"} in gt["pairs"]
    assert Path(gt["image"]).suffix == ".jpg"


def test_funsd_whole_archive_pack(server: FakeServer, tmp_path: Path) -> None:
    members = {}
    for i in range(8):
        sub = "testing_data" if i < 3 else "training_data"
        members[f"dataset/{sub}/images/f{i}.png"] = fake_bytes(str(i), 500)
        members[f"dataset/{sub}/annotations/f{i}.json"] = json.dumps({"form": []}).encode()
    m = with_sources("funsd", {"archive": {"url": server.add("/dataset.zip", make_zip(members))}},
                     sample_per_category=5)
    r = run(m, tmp_path, accept_eval_only=True)
    assert r.counts["forms"] == {"available": 8, "dev": 3, "heldout": 2}
    assert server.sent["/dataset.zip"] == len(server.files["/dataset.zip"])


def test_pubtabnet_pack(server: FakeServer, tmp_path: Path) -> None:
    names = [f"{i:064x}.png" for i in range(12)]
    gt = {n: {"html": "<table><tr><td>a</td></tr></table>", "type": "simple"} for n in names}
    zdata = make_zip({f"final_eval/{n}": fake_bytes(n, 100) for n in names})
    m = with_sources("pubtabnet-final-eval", {"gt": {"url": server.add("/final_eval.json", json.dumps(gt).encode())},
                                              "images": {"url": server.add("/final_eval.zip", zdata)}},
                     sample_per_category=10, exclude=[names[0]])
    r = run(m, tmp_path)
    assert r.counts["tables"] == {"available": 12, "dev": 6, "heldout": 4}
    raw = tmp_path / "data/raw/pubtabnet-final-eval"
    assert len(list((raw / "unpacked").rglob("*.png"))) == 10
    assert not (raw / "unpacked/final_eval.zip/final_eval" / names[0]).exists()
    from iris_eval.datasets.pubtabnet_final_eval import PubTabNetFinalEval

    pid = json.loads((tmp_path / "splits/pubtabnet-final-eval.json").read_text())["categories"]["tables"]["dev"][0]
    assert PubTabNetFinalEval().convert(raw, pid)["tables"][0]["cells"][0]["text"] == "a"


def test_tabrecset_planner_uses_english_originals_only(server: FakeServer, tmp_path: Path) -> None:
    members = {}
    for i in range(10):
        members[f"TabRecSet/image/English/all-line/e{i}.jpg"] = fake_bytes(f"e{i}", 300)
        members[f"TabRecSet/image/English/three-line/e{i}.jpg"] = fake_bytes(f"t{i}", 300)
        members[f"TabRecSet/image/Chinese/all-line/c{i}.jpg"] = fake_bytes(f"c{i}", 300)
        members[f"TabRecSet/TSR_TCR_annotation/English/e{i}.json"] = json.dumps({"shapes": [
            {"label": "1-1-1-2-Head-er", "group_id": 0}, {"label": "2-1-1-1-x", "group_id": 0}]}).encode()
    zdata = make_zip(members)
    api = {"files": [{"id": 7, "name": "TabRecSet (CurveTabSet).zip", "size": len(zdata),
                      "download_url": server.add("/files/7", zdata)},
                     {"id": 8, "name": "TableMe.zip", "size": 1, "download_url": "x"}]}
    server.add("/api/articles/20647788", json.dumps(api).encode())
    m = with_sources("tabrecset", {"archive": {"api": server.url("/api")}}, sample_per_category=5)
    r = run(m, tmp_path)
    assert r.counts == {"tables": {"available": 10, "dev": 3, "heldout": 2}}
    from iris_eval.datasets.tabrecset import TabRecSet

    raw = tmp_path / "data/raw/tabrecset"
    pid = next(iter(json.loads((raw / "pack.json").read_text())["files"]))
    gt = TabRecSet().convert(raw, pid)
    assert gt["text"] is None
    assert gt["tables"][0]["cells"][0] == {"row": 0, "col": 0, "rowSpan": 1, "colSpan": 2, "text": "Head-er"}


def test_layout_mismatch_stops_with_counts_not_guesses(server: FakeServer, tmp_path: Path) -> None:
    url = server.add("/FATURA2.zip", make_zip({"other/x.jpg": b"1", "other/y.json": b"{}"}))
    m = with_sources("fatura", {"archive": {"url": url}})
    with pytest.raises(FetchError, match="report this"):
        run(m, tmp_path)


def test_summary_is_one_screen() -> None:
    from iris_eval.pack.fetch import Result

    r = Result("fatura", "allowed", {"invoices": {"available": 200, "dev": 45, "heldout": 30}},
               {"invoices": {"dev": 30, "heldout": 20}}, 12_000_000, 13_000_000)
    text = summary([r], {"sroie": "excluded"})
    assert "fatura" in text and "45" in text and "NOT FETCHED" in text and len(text.splitlines()) <= 6


# ------------------------------------------------------------------ the command itself


def test_fetch_pack_runs_on_the_standard_library_only() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    out = subprocess.run([sys.executable, "-S", "-I", str(REPO / "eval" / "fetch_pack.py"), "--list"],
                         capture_output=True, text=True, env=env, check=True)
    assert "cord-v2" in out.stdout and "excluded" in out.stdout
    refused = subprocess.run([sys.executable, "-S", "-I", str(REPO / "eval" / "fetch_pack.py"), "sroie"],
                             capture_output=True, text=True, env=env)
    assert refused.returncode == 3 and "NOT FETCHED" in refused.stdout
    env.pop("IRIS_BLN600_PASSWORD", None)
    skip = subprocess.run([sys.executable, "-S", "-I", str(REPO / "eval" / "fetch_pack.py"), "bln600",
                           "--accept-eval-only"], capture_output=True, text=True, env=env)
    assert skip.returncode == 0 and "SKIPPED" in skip.stdout and "dataset page" in skip.stdout


def test_every_repo_manifest_has_a_pack_or_a_reason() -> None:
    from iris_eval.manifests import list_manifests

    for m in list_manifests():
        if m["use"] in ("allowed", "evaluation-only"):
            assert m.get("pack") or m.get("pack_reason"), m["id"]
            if m.get("pack"):
                assert m["converter"], m["id"]
    total = sum(m["pack"]["estimate"]["bytes"] for m in list_manifests() if m.get("pack"))
    assert total < 10 * 10**9
