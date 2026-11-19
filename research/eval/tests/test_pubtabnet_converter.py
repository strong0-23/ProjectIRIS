import json
from pathlib import Path

from PIL import Image

from iris_eval.datasets.pubtabnet_final_eval import PubTabNetFinalEval
from iris_eval.gt import GT_SCHEMA, parse_gt


def test_converts_synthetic_entries(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    imgs = raw / "unpacked" / "final_eval.zip" / "final_eval"
    imgs.mkdir(parents=True)
    for n in ("b.png", "a.png"):
        Image.new("RGB", (10, 10), "white").save(imgs / n)
    gt = {
        "b.png": {"html": "<html><body><table><tr><td><b>H</b></td><td>1</td></tr></table></body></html>",
                  "type": "simple"},
        "a.png": {"html": "<table><tr><td colspan=\"2\">X</td></tr><tr><td>y</td><td>z</td></tr></table>",
                  "type": "complex"},
    }
    (raw / "final_eval.json").write_text(json.dumps(gt))
    conv = PubTabNetFinalEval()
    assert conv.list_pages(raw) == [("a.png", "tables"), ("b.png", "tables")]
    g = conv.convert(raw, "a.png")
    assert g["text"] == {"lines": ["X", "y", "z"], "reading_order": True}
    assert g["tables"][0]["cells"][0] == {"row": 0, "col": 0, "rowSpan": 1, "colSpan": 2, "text": "X"}
    assert Path(g["image"]).name == "a.png"
    page = parse_gt({"schema": GT_SCHEMA, "id": "x/a.png", "dataset": "x", "category": "tables",
                     "split": "dev", **g})
    assert page.tables is not None and len(page.tables[0].cells) == 3
    assert conv.convert(raw, "b.png")["text"]["lines"] == ["H", "1"]
