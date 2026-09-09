"""MathVisualizer 的 Agent 工具壳；校验与清洗均由 service 完成。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from tools.base_tool import BaseTool, ToolCapability, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


class VisualViewportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x_min: float
    x_max: float
    y_min: float
    y_max: float


class VisualSeriesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["curve", "line", "area", "vector", "sequence", "polygon"]
    label: str = ""
    points: list[tuple[float, float]] = Field(
        ...,
        description="已采样坐标，如 [[-2,4],[-1,1],[0,0],[1,1],[2,4]]；不得传表达式或代码",
    )


class VisualAnnotationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["point", "label", "interval"]
    x: float
    y: float
    label: str = ""
    x_end: Optional[float] = None
    y_end: Optional[float] = None


class MathVisualSpecInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal[
        "function_plot",
        "tangent_line",
        "area_under_curve",
        "vector_plot",
        "sequence_plot",
        "geometry_plot",
    ]
    title: str
    viewport: VisualViewportInput
    series: list[VisualSeriesInput]
    annotations: list[VisualAnnotationInput] = Field(default_factory=list)
    teaching_note: str = ""
    verification_request: Optional[Dict[str, Any]] = None
    verified_values: Optional[Dict[str, float]] = None


class MathVisualizeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: MathVisualSpecInput


class MathVisualizeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., description="图形的教学目的")
    parameters: MathVisualizeParameters


class MathVisualizeTool(BaseTool):
    name = "math_visualize"
    description = (
        "生成安全的数学静态可视化。parameters.spec 必须提供已采样坐标的 MathVisualSpec，"
        "支持 function_plot、tangent_line、area_under_curve、vector_plot、"
        "sequence_plot、geometry_plot；禁止传 JavaScript、HTML 或待前端求值的表达式。"
        "切线和积分关键数据必须附 verification_request，工具会独立调用 MathVerifier。"
    )
    version = "1.0.0"
    capabilities = [ToolCapability.NUMERICAL_COMPUTATION, ToolCapability.PLOTTING]
    args_schema = MathVisualizeArgs

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [cap.value for cap in self.capabilities],
            "input_schema": self.args_schema.model_json_schema(),
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        from app.services.math_visualizer import MathVisualValidationError, get_math_visualizer

        request = dict(input_data.parameters or {})
        nested = request.get("parameters")
        if isinstance(nested, BaseModel):
            nested = nested.model_dump(exclude_none=True)
        if isinstance(nested, dict):
            request = nested
        raw_spec = request.get("spec", request)
        if isinstance(raw_spec, BaseModel):
            raw_spec = raw_spec.model_dump(exclude_none=True)
        try:
            payload = get_math_visualizer().visualize(raw_spec)
        except MathVisualValidationError as exc:
            payload = {
                "visualization_status": "failed",
                "spec": None,
                "message": str(exc),
            }
            logger.warning("MathVisualizer 规格被拒绝: reason=%s", str(exc)[:240])

        sink = input_data.context.get("visualizations")
        if isinstance(sink, list):
            sink.append(payload)
        return ToolOutput(
            success=True,
            result=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            data=payload,
            tool_name=self.name,
            metadata={"visualization_status": payload["visualization_status"]},
        )
