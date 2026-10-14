"""Optional PDF layout/OCR sidecar contract.

This process intentionally does not ship a heavyweight model. Set
``LAYOUT_ENGINE`` to an adapter installed in the worker image when deploying
PaddleOCR/PP-StructureV3. The main application depends only on this contract
and can always fall back locally.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="Math AI Layout Worker", version="0.1")


@app.get("/health")
async def health() -> dict[str, Any]:
    engine = (os.getenv("LAYOUT_ENGINE") or "disabled").strip().lower()
    if engine in {"", "disabled", "none"}:
        return {"status": "degraded", "engine": None, "capabilities": []}
    if engine == "pp_structure_v3":
        from pp_structure_v3_adapter import formula_enabled, is_available
        if not is_available():
            return {"status": "degraded", "engine": engine, "capabilities": [], "reason": "paddleocr_not_installed"}
        capabilities = ["layout", "ocr", "question_regions"]
        if formula_enabled():
            capabilities.append("formula")
        return {"status": "ready", "engine": engine, "capabilities": capabilities}
    return {"status": "ready", "engine": engine, "capabilities": ["layout", "ocr", "question_regions"]}


@app.post("/v1/parse")
async def parse(file: UploadFile = File(...)) -> dict[str, Any]:
    engine = (os.getenv("LAYOUT_ENGINE") or "disabled").strip().lower()
    if engine in {"", "disabled", "none"}:
        raise HTTPException(status_code=503, detail={"code": "LAYOUT_ENGINE_NOT_CONFIGURED", "message": "未配置版面解析引擎"})
    if engine != "pp_structure_v3":
        raise HTTPException(status_code=501, detail={"code": "LAYOUT_ENGINE_ADAPTER_NOT_INSTALLED", "message": f"未安装引擎适配器: {engine}"})
    try:
        from pp_structure_v3_adapter import parse_pdf
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(await file.read())
            temp_path = handle.name
        try:
            return parse_pdf(temp_path)
        finally:
            os.unlink(temp_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={"code": "LAYOUT_PARSE_FAILED", "message": str(exc)[:1000]}) from exc
