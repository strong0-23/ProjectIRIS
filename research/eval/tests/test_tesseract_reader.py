import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from iris_eval.docmodel import parse_document
from iris_eval.readers.tesseract import TesseractReader, tsv_to_document
from iris_eval.textmetrics import score_text

TSV = "\n".join([
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    "1\t1\t0\t0\t0\t0\t0\t0\t200\t100\t-1\t",
    "2\t1\t1\t0\t0\t0\t10\t10\t100\t40\t-1\t",
    "3\t1\t1\t1\t0\t0\t10\t10\t100\t40\t-1\t",
    "4\t1\t1\t1\t1\t0\t10\t10\t100\t20\t-1\t",
    "5\t1\t1\t1\t1\t1\t10\t10\t40\t20\t96.5\tHello",
    "5\t1\t1\t1\t1\t2\t60\t10\t50\t20\t41.0\twor1d",
    "4\t1\t1\t1\t2\t0\t10\t30\t100\t20\t-1\t",
    "5\t1\t1\t1\t2\t1\t10\t30\t40\t20\t-1\t ",
])


def test_tsv_to_document() -> None:
    d = tsv_to_document(TSV)
    page = d["pages"][0]
    assert (page["width"], page["height"]) == (200, 100)
    assert len(page["blocks"]) == 1
    lines = page["blocks"][0]["lines"]
    assert len(lines) == 1  # the empty line is dropped
    assert lines[0]["text"] == "Hello wor1d"
    assert lines[0]["words"][1]["confidence"] == pytest.approx(0.41)
    assert lines[0]["words"][0]["box"] == [10, 10, 50, 30]


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_reads_a_synthetic_page(tmp_path: Path) -> None:
    img = Image.new("RGB", (1200, 300), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=48)
    draw.text((40, 40), "Synthetic invoice 2026", fill="black", font=font)
    draw.text((40, 150), "Amount due 123.45", fill="black", font=font)
    path = tmp_path / "page.png"
    img.save(path)
    reader = TesseractReader()
    d = reader.read(path)
    assert d["source"]["timings"]["totalSeconds"] > 0
    assert d["source"]["models"][0]["sizeBytes"] > 0
    p = parse_document(d)
    ts = score_text(["Synthetic invoice 2026", "Amount due 123.45"], p.lines, True)
    assert ts.cer is not None and ts.cer < 0.1
