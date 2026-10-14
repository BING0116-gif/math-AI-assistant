from layout_worker.pp_structure_v3_adapter import _bbox, _blocks_from_result, formula_enabled


def test_bbox_normalizes_polygon_and_rectangle():
    assert _bbox([1, 2, 10, 20]) == [1.0, 2.0, 10.0, 20.0]
    assert _bbox([[1, 2], [10, 2], [10, 20], [1, 20]]) == [1.0, 2.0, 10.0, 20.0]


def test_structure_result_keeps_text_formula_and_confidence():
    blocks = _blocks_from_result({
        "overall_ocr_res": {
            "rec_texts": ["7. 设 f(x)"],
            "rec_boxes": [[1, 2, 100, 30]],
            "rec_scores": [0.98],
        },
        "formula_res_list": [{"rec_formula": r"$x^2$", "bbox": [2, 31, 80, 55], "score": 0.91}],
    })
    assert blocks[0]["text"] == "7. 设 f(x)"
    assert blocks[0]["confidence"] == 0.98
    assert blocks[1]["kind"] == "equation"


def test_formula_recognition_is_opt_in(monkeypatch):
    monkeypatch.delenv("LAYOUT_FORMULA_RECOGNITION", raising=False)
    assert formula_enabled() is False
    monkeypatch.setenv("LAYOUT_FORMULA_RECOGNITION", "true")
    assert formula_enabled() is True
