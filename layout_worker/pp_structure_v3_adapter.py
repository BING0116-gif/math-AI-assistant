"""PP-StructureV3 adapter loaded only inside layout-worker."""

from __future__ import annotations

import threading
import os
from pathlib import Path
from typing import Any

_pipeline = None
_pipeline_lock = threading.Lock()


def formula_enabled() -> bool:
    return (os.getenv("LAYOUT_FORMULA_RECOGNITION") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                from paddleocr import PPStructureV3

                _pipeline = PPStructureV3(
                    lang="ch",
                    layout_detection_model_name="PP-DocLayout-S",
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    text_recognition_model_name="PP-OCRv5_mobile_rec",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    use_formula_recognition=formula_enabled(),
                    use_table_recognition=False,
                    use_region_detection=False,
                    device="cpu",
                    enable_mkldnn=False,
                    cpu_threads=4,
                )
    return _pipeline


def is_available() -> bool:
    try:
        import paddleocr  # noqa: F401
        return True
    except Exception:
        return False


def _run_pipeline(path: str | Path) -> list[dict[str, Any]]:
    pipeline = _get_pipeline()
    output: list[dict[str, Any]] = []
    for page_index, result in enumerate(pipeline.predict(input=str(path))):
        raw = _result_dict(result)
        blocks = _blocks_from_result(raw)
        page = page_index + 1
        for block in blocks:
            block["page"] = page
        page_text = "\n".join(str(block["text"]) for block in blocks if block.get("text"))
        output.append({"page": page, "text": page_text, "markdown": _markdown_from_result(raw), "blocks": blocks})
    return output


def parse_pdf(path: str | Path) -> dict[str, Any]:
    pages = _run_pipeline(path)
    blocks = [block for page in pages for block in page["blocks"]]
    return {
        "parser_name": "pp_structure_v3",
        "parser_version": "paddleocr",
        "markdown": "\n\n".join(page["markdown"] or page["text"] for page in pages),
        "pages": [{"page": page["page"], "text": page["text"]} for page in pages],
        "blocks": blocks,
        "page_mapping_uncertain": False,
    }


def _result_dict(result: Any) -> dict[str, Any]:
    raw = getattr(result, "json", None)
    if callable(raw):
        raw = raw()
    if isinstance(raw, dict):
        return raw.get("res", raw)
    if isinstance(result, dict):
        return result.get("res", result)
    return {}


def _markdown_from_result(raw: dict[str, Any]) -> str:
    markdown = raw.get("markdown")
    if isinstance(markdown, str):
        return markdown
    if isinstance(markdown, dict):
        for key in ("markdown_texts", "text", "content"):
            if isinstance(markdown.get(key), str):
                return markdown[key]
    return ""


def _blocks_from_result(raw: dict[str, Any]) -> list[dict[str, Any]]:
    ocr = raw.get("overall_ocr_res") or {}
    texts = ocr.get("rec_texts") or []
    boxes = ocr.get("rec_boxes") or ocr.get("rec_polys") or []
    blocks: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        bbox = _bbox(boxes[index]) if index < len(boxes) else None
        blocks.append({"text": str(text), "kind": "text", "bbox": bbox, "confidence": _score(ocr, index)})
    for item in raw.get("formula_res_list") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("rec_formula") or item.get("formula") or item.get("text")
        if text:
            blocks.append({"text": str(text), "kind": "equation", "bbox": _bbox(item.get("bbox") or item.get("coordinate")), "confidence": item.get("score")})
    return blocks


def _bbox(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        if len(value) == 4 and not isinstance(value[0], (list, tuple)):
            return [float(v) for v in value]
        points = [point for point in value if len(point) >= 2]
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        return [min(xs), min(ys), max(xs), max(ys)] if xs and ys else None
    except (TypeError, ValueError):
        return None


def _score(ocr: dict[str, Any], index: int) -> float | None:
    scores = ocr.get("rec_scores") or []
    try:
        return float(scores[index]) if index < len(scores) else None
    except (TypeError, ValueError):
        return None
