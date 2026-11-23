"""Per-dataset page listing for data packs.

A planner lists every page a dataset offers (its native ID, IRIS category and, for grouped
splits, its group) from archive directories, file names or small index files, and names the
files each page needs. It never looks at page content: the split rule then picks pages by ID.

Layouts were taken from each dataset's documentation (see the manifest notes) and could not be
checked against the real archives from the sandbox. Where a layout assumption fails, the planner
stops with counts of what it found (never a guess), so the owner can report it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from .remote import FetchError
from .sources import Context, FileRef

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


@dataclass
class Page:
    id: str
    category: str
    files: list[FileRef]
    group: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


def _junk(name: str) -> bool:
    p = PurePosixPath(name)
    return "__MACOSX" in p.parts or p.name.startswith("._") or p.name == ".DS_Store"


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", s.lower())


def by_folder_stem(names: Iterable[str], folder: str | None, exts: tuple[str, ...]) -> dict[str, str]:
    """Map file stem -> member name for members with one of ``exts`` under a folder named ``folder``
    (any ancestor, compared case- and separator-insensitively). The first extension in ``exts``
    wins when one stem has several files."""
    out: dict[str, str] = {}
    rank: dict[str, int] = {}
    want = _norm(folder) if folder else None
    for n in sorted(names):
        if _junk(n):
            continue
        p = PurePosixPath(n)
        ext = p.suffix.lower()
        if ext not in exts:
            continue
        if want is not None and want not in {_norm(x) for x in p.parts[:-1]}:
            continue
        r = exts.index(ext)
        if p.stem not in out or r < rank[p.stem]:
            out[p.stem], rank[p.stem] = n, r
    return out


def _need(found: dict[str, str], what: str, ctx: Context, source: str) -> None:
    if not found:
        folders = sorted({PurePosixPath(n).parts[0] for n in ctx.names(source) if not _junk(n)})[:12]
        raise FetchError(
            f"{ctx.dataset}: expected {what} in {source!r} but found none; top-level folders: {folders}. "
            "The archive layout differs from the documented one: report this to the orchestrator."
        )


def _whole_ref(ctx: Context, source: str, role: str) -> FileRef:
    return FileRef(source, None, ctx.source(source)["dest"], role)


# ---------------------------------------------------------------------------- planners


def pubtabnet(ctx: Context) -> list[Page]:
    with ctx.file_path("gt").open(encoding="utf-8") as f:
        names = sorted(json.load(f))
    members = {PurePosixPath(n).name: n for n in ctx.names("images") if n.endswith(".png") and not _junk(n)}
    gt = _whole_ref(ctx, "gt", "gt")
    pages = []
    for name in names:
        files = [gt]
        if name in members:
            files.append(FileRef("images", members[name], f"unpacked/final_eval.zip/{members[name]}", "image"))
        pages.append(Page(name, "tables", files))
    return pages


def cord(ctx: Context) -> list[Page]:
    pages = []
    for shard, n in sorted(ctx.pack["rows"].items()):
        ref = _whole_ref(ctx, shard, "shard")
        pages += [Page(f"{shard}/{i:03d}", "receipts", [ref], attrs={"shard": shard, "row": i}) for i in range(n)]
    return pages


def doclaynet(ctx: Context) -> list[Page]:
    core = ctx.names("core")
    coco_name = [n for n in core if n.replace("\\", "/").lower().endswith("coco/test.json") and not _junk(n)]
    if len(coco_name) != 1:
        raise FetchError(f"{ctx.dataset}: expected one COCO/test.json in core, found {len(coco_name)}")
    with ctx.read_member("core", coco_name[0]).open(encoding="utf-8") as f:
        images = json.load(f)["images"]
    pngs = by_folder_stem(core, "PNG", (".png",))
    cells = by_folder_stem(ctx.names("extra"), "JSON", (".json",))
    _need(pngs, "PNG/<hash>.png", ctx, "core")
    _need(cells, "JSON/<hash>.json", ctx, "extra")
    pages: dict[str, Page] = {}
    for img in images:
        if img.get("precedence", 0) not in (0, None):
            continue  # a second or third annotation of a page
        stem = PurePosixPath(str(img["file_name"])).stem
        if stem in pages or stem not in pngs or stem not in cells:
            continue
        pages[stem] = Page(stem, "letters-and-reports",
                           [ctx.member_ref("core", pngs[stem], "image"), ctx.member_ref("extra", cells[stem], "cells")],
                           attrs={"doc_category": img.get("doc_category")})
    return [pages[k] for k in sorted(pages)]


def fatura(ctx: Context) -> list[Page]:
    names = ctx.names("archive")
    rx = re.compile(ctx.pack.get("image_regex", r"(?:^|/)images/(Template(\d+)_Instance(\d+))\.jpg$"))
    anns = by_folder_stem(names, "Original_Format", (".json",))
    _need(anns, "Annotations/Original_Format/<id>.json", ctx, "archive")
    pages = []
    for n in sorted(names):
        m = rx.search(n)
        if not m or _junk(n) or m.group(1) not in anns:
            continue
        pid = m.group(1)
        pages.append(Page(pid, "invoices",
                          [ctx.member_ref("archive", n, "image"), ctx.member_ref("archive", anns[pid], "annotation")],
                          group=f"Template{int(m.group(2))}"))
    if not pages:
        _need({}, "images/Template<t>_Instance<i>.jpg", ctx, "archive")
    return pages


def smartdoc(ctx: Context) -> list[Page]:
    infos = {i.filename: i for i in ctx.infolist("archive") if not _junk(i.filename)}
    images = by_folder_stem(infos, None, (".jpg", ".jpeg", ".png"))
    texts = by_folder_stem(infos, None, (".txt",))
    pages = []
    for stem, img in sorted(images.items()):
        if stem not in texts:
            continue
        gt = infos[texts[stem]]
        # Identical ground-truth text = same source document. The CRC-32 and size come from the
        # archive directory, so captures are grouped without opening any file.
        pages.append(Page(stem, "phone-photos-hard",
                          [ctx.member_ref("archive", img, "image"), ctx.member_ref("archive", texts[stem], "text")],
                          group=f"{gt.CRC:08x}-{gt.file_size}"))
    if not pages:
        raise FetchError(f"{ctx.dataset}: {len(images)} images and {len(texts)} text files, none matched by name; "
                         "report this to the orchestrator")
    expected = ctx.pack.get("expected_groups")
    groups = {p.group for p in pages}
    if expected is not None and len(groups) != expected:
        raise FetchError(
            f"{ctx.dataset}: grouping captures by ground-truth file gave {len(groups)} documents, expected "
            f"{expected}; the split by document cannot be trusted. Report this to the orchestrator."
        )
    return pages


_TABRECSET_SKIP = ("three", "noline", "generated", "tsr", "tdannotation", "chinese")


def tabrecset(ctx: Context) -> list[Page]:
    names = [n for n in ctx.names("archive") if not _junk(n)]

    def parts(n: str) -> set[str]:
        return {_norm(x) for x in PurePosixPath(n).parts[:-1]}

    def original_english(n: str) -> bool:
        ps = parts(n)
        return "english" in ps and not any(any(s in x for s in _TABRECSET_SKIP) for x in ps)

    imgs = sorted(n for n in names if PurePosixPath(n).suffix.lower() in IMAGE_EXTS and original_english(n))
    anns = {PurePosixPath(n).stem: n for n in sorted(names)
            if n.lower().endswith(".json") and "english" in parts(n) and any("tsr" in x for x in parts(n))}
    _need(anns, "TSR_TCR_annotation/.../English/<name>.json", ctx, "archive")
    stems = [PurePosixPath(n).stem for n in imgs]
    if len(set(stems)) != len(stems):
        raise FetchError(f"{ctx.dataset}: image names are not unique among English originals; report this")
    pages = []
    for n in imgs:
        stem = PurePosixPath(n).stem
        if stem in anns:
            pages.append(Page(stem, "tables", [ctx.member_ref("archive", n, "image"),
                                               ctx.member_ref("archive", anns[stem], "annotation")]))
    if not pages:
        _need({}, "English original images with a TSR_TCR annotation", ctx, "archive")
    return pages


def funsd(ctx: Context) -> list[Page]:
    names = ctx.names("archive")
    imgs = by_folder_stem(names, "images", (".png",))
    anns = by_folder_stem(names, "annotations", (".json",))
    _need(imgs, "dataset/*/images/<id>.png", ctx, "archive")
    pages = []
    for stem in sorted(set(imgs) & set(anns)):
        subset = "testing" if "testing" in imgs[stem] else "training"
        pages.append(Page(stem, "forms", [ctx.member_ref("archive", imgs[stem], "image"),
                                          ctx.member_ref("archive", anns[stem], "annotation")],
                          attrs={"subset": subset}))
    return pages


def omnidocbench(ctx: Context) -> list[Page]:
    with ctx.file_path("gt").open(encoding="utf-8") as f:
        data = json.load(f)
    langs = set(ctx.pack.get("languages", ["english"]))
    cmap: dict[str, str] = ctx.pack["category_map"]
    gt = _whole_ref(ctx, "gt", "gt")
    pages: dict[str, Page] = {}
    for item in data:
        pi = item.get("page_info") or {}
        attr = pi.get("page_attribute") or {}
        path = str(pi.get("image_path") or "").replace("\\", "/").removeprefix("images/")
        cat = cmap.get(str(attr.get("data_source")))
        if not path or cat is None or attr.get("language") not in langs or path in pages:
            continue
        pages[path] = Page(path, cat, [gt, ctx.member_ref("images", path, "image")],
                           attrs={"data_source": attr.get("data_source")})
    return [pages[k] for k in sorted(pages)]


def bln600(ctx: Context) -> list[Page]:
    names = ctx.names("archive")
    imgs = by_folder_stem(names, "Images", (".jpg", ".jpeg", ".tif", ".tiff", ".png"))
    gts = by_folder_stem(names, "Ground Truth", (".txt",))
    _need(imgs, "Images/<id>.jpg|tif", ctx, "archive")
    _need(gts, "Ground Truth/<id>.txt", ctx, "archive")
    return [Page(stem, "book-or-scanned-pages", [ctx.member_ref("archive", imgs[stem], "image"),
                                                 ctx.member_ref("archive", gts[stem], "text")])
            for stem in sorted(set(imgs) & set(gts))]


PLANNERS: dict[str, Callable[[Context], list[Page]]] = {
    "pubtabnet": pubtabnet,
    "cord": cord,
    "doclaynet": doclaynet,
    "fatura": fatura,
    "smartdoc": smartdoc,
    "tabrecset": tabrecset,
    "funsd": funsd,
    "omnidocbench": omnidocbench,
    "bln600": bln600,
}
