"""T08 MathVisualizer：校验并清洗供前端原生 SVG 渲染的纯数据规格。"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any, Mapping, Sequence

from app.services.math_verifier import VERIFIED, get_math_verifier

VISUAL_TYPES = frozenset(
    {
        "function_plot",
        "tangent_line",
        "area_under_curve",
        "vector_plot",
        "sequence_plot",
        "geometry_plot",
    }
)
SERIES_KINDS = frozenset({"curve", "line", "area", "vector", "sequence", "polygon"})
ANNOTATION_KINDS = frozenset({"point", "label", "interval"})
INTERACTION_KINDS = frozenset({"parameter_slider", "step_sequence"})
TYPE_SERIES_KINDS = {
    "function_plot": frozenset({"curve", "line"}),
    "tangent_line": frozenset({"curve", "line"}),
    "area_under_curve": frozenset({"curve", "line", "area"}),
    "vector_plot": frozenset({"vector", "line"}),
    "sequence_plot": frozenset({"sequence", "line"}),
    "geometry_plot": frozenset({"line", "curve", "polygon"}),
}

MAX_POINTS_PER_SERIES = 600
MAX_TOTAL_POINTS = 1800
MAX_ABS_COORDINATE = 1_000_000.0
MAX_TEXT_LENGTH = 240
MAX_INTERACTION_FRAMES = 24
_EXECUTABLE_TEXT = re.compile(
    r"(?:<\s*/?\s*(?:script|iframe|object|embed|svg)|javascript\s*:|"
    r"(?:document|window)\s*\.|\beval\s*\(|=>|\bon\w+\s*=)",
    re.IGNORECASE,
)
_LABELED_POINT = re.compile(
    r"[\(（]\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*[,，]\s*"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*[\)）]"
)


class MathVisualValidationError(ValueError):
    """可视化规格不满足白名单或安全边界。"""


class MathVisualizer:
    """把模型提供的坐标规格收敛为有限、受控、不可执行的渲染数据。"""

    def visualize(self, raw_spec: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(raw_spec, Mapping):
            raise MathVisualValidationError("MathVisualSpec 必须是对象")

        spec = deepcopy(dict(raw_spec))
        visual_type = str(spec.get("type") or "").strip()
        if visual_type not in VISUAL_TYPES:
            raise MathVisualValidationError(f"不支持的可视化类型：{visual_type or 'missing'}")

        viewport = self._clean_viewport(spec.get("viewport"))
        title = self._clean_text(spec.get("title"), "title", required=True)
        note = self._clean_text(spec.get("teaching_note", ""), "teaching_note")
        raw_series = spec.get("series")
        if not isinstance(raw_series, Sequence) or isinstance(raw_series, (str, bytes)) or not raw_series:
            raise MathVisualValidationError("series 必须是非空数组")

        partial = False
        total_points = 0
        cleaned_series: list[dict[str, Any]] = []
        allowed_kinds = TYPE_SERIES_KINDS[visual_type]
        for index, item in enumerate(raw_series):
            cleaned, was_partial = self._clean_series(item, viewport, allowed_kinds, index)
            total_points += len(cleaned["points"])
            if total_points > MAX_TOTAL_POINTS:
                raise MathVisualValidationError(f"总点数不能超过 {MAX_TOTAL_POINTS}")
            partial = partial or was_partial
            cleaned_series.append(cleaned)

        raw_annotations = spec.get("annotations") or []
        if not isinstance(raw_annotations, Sequence) or isinstance(raw_annotations, (str, bytes)):
            raise MathVisualValidationError("annotations 必须是数组")
        annotations = [self._clean_annotation(item, viewport, i) for i, item in enumerate(raw_annotations)]
        annotations, annotations_partial = self._reconcile_annotations(annotations, cleaned_series)
        partial = partial or annotations_partial

        interaction, interaction_partial = self._clean_interaction(
            spec.get("interaction"),
            viewport,
            allowed_kinds,
            visual_type,
        )
        partial = partial or interaction_partial

        verification = self._verify_critical_data(visual_type, spec, cleaned_series)
        cleaned_spec = {
            "type": visual_type,
            "title": title,
            "viewport": viewport,
            "series": cleaned_series,
            "annotations": annotations,
            "teaching_note": note,
        }
        if interaction is not None:
            cleaned_spec["interaction"] = interaction
        return {
            "visualization_status": "partial" if partial else "ok",
            "spec": cleaned_spec,
            "verification": verification,
        }

    def _clean_interaction(
        self,
        raw: Any,
        viewport: Mapping[str, float],
        allowed_kinds: frozenset[str],
        visual_type: str,
    ) -> tuple[dict[str, Any] | None, bool]:
        """校验预计算交互帧；浏览器永远只切换纯坐标，不执行表达式。"""
        if raw is None:
            return None, False
        if not isinstance(raw, Mapping):
            raise MathVisualValidationError("interaction 必须是对象")
        kind = str(raw.get("kind") or "").strip()
        if kind not in INTERACTION_KINDS:
            raise MathVisualValidationError("interaction.kind 不在白名单中")
        parameter = self._clean_text(raw.get("parameter", ""), "interaction.parameter", required=True)
        label = self._clean_text(raw.get("label", parameter), "interaction.label", required=True)
        raw_frames = raw.get("frames")
        if not isinstance(raw_frames, Sequence) or isinstance(raw_frames, (str, bytes)) or not raw_frames:
            raise MathVisualValidationError("interaction.frames 必须是非空数组")
        if len(raw_frames) > MAX_INTERACTION_FRAMES:
            raise MathVisualValidationError(f"交互帧不能超过 {MAX_INTERACTION_FRAMES}")
        frames: list[dict[str, Any]] = []
        partial = False
        for frame_index, frame in enumerate(raw_frames):
            if not isinstance(frame, Mapping):
                raise MathVisualValidationError(f"interaction.frames[{frame_index}] 必须是对象")
            value = self._finite_number(frame.get("value"), f"interaction.frames[{frame_index}].value")
            title = self._clean_text(frame.get("title", ""), f"interaction.frames[{frame_index}].title")
            note = self._clean_text(frame.get("teaching_note", ""), f"interaction.frames[{frame_index}].teaching_note")
            raw_frame_series = frame.get("series")
            if not isinstance(raw_frame_series, Sequence) or isinstance(raw_frame_series, (str, bytes)) or not raw_frame_series:
                raise MathVisualValidationError(f"interaction.frames[{frame_index}].series 必须是非空数组")
            cleaned_series: list[dict[str, Any]] = []
            frame_total_points = 0
            for series_index, item in enumerate(raw_frame_series):
                cleaned, was_partial = self._clean_series(item, viewport, allowed_kinds, series_index)
                partial = partial or was_partial
                frame_total_points += len(cleaned["points"])
                if frame_total_points > MAX_TOTAL_POINTS:
                    raise MathVisualValidationError(
                        f"interaction.frames[{frame_index}] 总点数不能超过 {MAX_TOTAL_POINTS}"
                    )
                cleaned_series.append(cleaned)
            raw_annotations = frame.get("annotations") or []
            if not isinstance(raw_annotations, Sequence) or isinstance(raw_annotations, (str, bytes)):
                raise MathVisualValidationError(f"interaction.frames[{frame_index}].annotations 必须是数组")
            annotations = [self._clean_annotation(item, viewport, i) for i, item in enumerate(raw_annotations)]
            annotations, annotation_partial = self._reconcile_annotations(annotations, cleaned_series)
            partial = partial or annotation_partial
            frames.append({
                "value": value,
                "title": title,
                "teaching_note": note,
                "series": cleaned_series,
                "annotations": annotations,
            })

        values = [frame["value"] for frame in frames]
        if len(set(values)) != len(values):
            raise MathVisualValidationError("interaction.frames.value 不能重复")
        if kind == "parameter_slider" and len(frames) < 2:
            raise MathVisualValidationError("parameter_slider 至少需要 2 个交互帧")
        raw_steps = raw.get("steps") or []
        if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
            raise MathVisualValidationError("interaction.steps 必须是数组")
        steps: list[dict[str, Any]] = []
        for step_index, step in enumerate(raw_steps):
            if not isinstance(step, Mapping):
                raise MathVisualValidationError(f"interaction.steps[{step_index}] 必须是对象")
            frame_index = step.get("frame_index")
            if isinstance(frame_index, bool) or not isinstance(frame_index, int) or not 0 <= frame_index < len(frames):
                raise MathVisualValidationError(f"interaction.steps[{step_index}].frame_index 无效")
            steps.append({
                "frame_index": frame_index,
                "title": self._clean_text(step.get("title", ""), f"interaction.steps[{step_index}].title", required=True),
                "explanation": self._clean_text(step.get("explanation", ""), f"interaction.steps[{step_index}].explanation", required=True),
            })
        return {
            "kind": kind,
            "parameter": parameter,
            "label": label,
            "frames": frames,
            "steps": steps,
        }, partial

    def _clean_viewport(self, raw: Any) -> dict[str, float]:
        if not isinstance(raw, Mapping):
            raise MathVisualValidationError("viewport 必须是对象")
        values = {}
        for key in ("x_min", "x_max", "y_min", "y_max"):
            values[key] = self._finite_number(raw.get(key), f"viewport.{key}")
            if abs(values[key]) > MAX_ABS_COORDINATE:
                raise MathVisualValidationError(f"viewport.{key} 超出允许范围")
        if values["x_min"] >= values["x_max"] or values["y_min"] >= values["y_max"]:
            raise MathVisualValidationError("viewport 最小值必须小于最大值")
        return values

    def _clean_series(
        self,
        raw: Any,
        viewport: Mapping[str, float],
        allowed_kinds: frozenset[str],
        index: int,
    ) -> tuple[dict[str, Any], bool]:
        if not isinstance(raw, Mapping):
            raise MathVisualValidationError(f"series[{index}] 必须是对象")
        kind = str(raw.get("kind") or "").strip()
        if kind not in SERIES_KINDS or kind not in allowed_kinds:
            raise MathVisualValidationError(f"series[{index}].kind 不在当前图形白名单中")
        label = self._clean_text(raw.get("label", ""), f"series[{index}].label")
        points = raw.get("points")
        if not isinstance(points, Sequence) or isinstance(points, (str, bytes)) or not points:
            raise MathVisualValidationError(f"series[{index}].points 必须是非空数组")
        if len(points) > MAX_POINTS_PER_SERIES:
            raise MathVisualValidationError(f"单个序列点数不能超过 {MAX_POINTS_PER_SERIES}")

        cleaned: list[list[float]] = []
        partial = False
        for point_index, point in enumerate(points):
            if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) != 2:
                raise MathVisualValidationError(f"series[{index}].points[{point_index}] 必须是 [x, y]")
            x = self._finite_number(point[0], f"series[{index}].points[{point_index}][0]")
            y = self._finite_number(point[1], f"series[{index}].points[{point_index}][1]")
            if abs(x) > MAX_ABS_COORDINATE or abs(y) > MAX_ABS_COORDINATE:
                raise MathVisualValidationError(f"series[{index}] 存在超出全局范围的坐标")
            clipped_x = min(max(x, viewport["x_min"]), viewport["x_max"])
            clipped_y = min(max(y, viewport["y_min"]), viewport["y_max"])
            partial = partial or clipped_x != x or clipped_y != y
            candidate = [clipped_x, clipped_y]
            if not cleaned or candidate != cleaned[-1]:
                cleaned.append(candidate)

        minimum = 3 if kind in {"area", "polygon"} else 2
        if kind == "sequence":
            minimum = 1
        if len(cleaned) < minimum:
            raise MathVisualValidationError(f"series[{index}] 清洗后点数不足")
        return {"kind": kind, "label": label, "points": cleaned}, partial

    def _clean_annotation(self, raw: Any, viewport: Mapping[str, float], index: int) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise MathVisualValidationError(f"annotations[{index}] 必须是对象")
        kind = str(raw.get("kind") or "").strip()
        if kind not in ANNOTATION_KINDS:
            raise MathVisualValidationError(f"annotations[{index}].kind 不在白名单中")
        label = self._clean_text(raw.get("label", ""), f"annotations[{index}].label")
        result: dict[str, Any] = {"kind": kind, "label": label}
        for key, lower, upper in (
            ("x", viewport["x_min"], viewport["x_max"]),
            ("y", viewport["y_min"], viewport["y_max"]),
            ("x_end", viewport["x_min"], viewport["x_max"]),
            ("y_end", viewport["y_min"], viewport["y_max"]),
        ):
            if key in raw:
                value = self._finite_number(raw[key], f"annotations[{index}].{key}")
                if value < lower or value > upper:
                    raise MathVisualValidationError(f"annotations[{index}].{key} 超出 viewport")
                result[key] = value
        if "x" not in result or "y" not in result:
            raise MathVisualValidationError(f"annotations[{index}] 缺少 x/y")
        return result

    def _verify_critical_data(
        self,
        visual_type: str,
        raw_spec: Mapping[str, Any],
        series: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any] | None:
        if visual_type not in {"tangent_line", "area_under_curve"}:
            return None
        request = raw_spec.get("verification_request")
        if not isinstance(request, Mapping):
            raise MathVisualValidationError("关键数学标注缺少 verification_request")
        verifier = get_math_verifier()
        result = verifier.verify(request)
        if result.status != VERIFIED:
            raise MathVisualValidationError(f"关键数学标注未通过 MathVerifier：{result.status}")

        if visual_type == "tangent_line":
            values = raw_spec.get("verified_values")
            if not isinstance(values, Mapping):
                raise MathVisualValidationError("切线图缺少 verified_values")
            tangent_x = self._finite_number(values.get("tangent_x"), "verified_values.tangent_x")
            tangent_y = self._finite_number(values.get("tangent_y"), "verified_values.tangent_y")
            slope = self._finite_number(values.get("slope"), "verified_values.slope")
            derivative = request.get("claimed", request.get("derivative"))
            variable = str(request.get("variable") or "x")
            slope_check = verifier.verify(
                {
                    "type": "function_value",
                    "expression": derivative,
                    "values": {variable: tangent_x},
                    "claimed": slope,
                }
            )
            value_check = verifier.verify(
                {
                    "type": "function_value",
                    "expression": request.get("expression"),
                    "values": {variable: tangent_x},
                    "claimed": tangent_y,
                }
            )
            if slope_check.status != VERIFIED or value_check.status != VERIFIED:
                raise MathVisualValidationError("切点或斜率与 MathVerifier 结果不一致")
            line = next((item for item in series if item["kind"] == "line"), None)
            if line is None:
                raise MathVisualValidationError("切线图必须包含 line 序列")
            (x1, y1), (x2, y2) = line["points"][0], line["points"][-1]
            if x1 == x2 or not self._close((y2 - y1) / (x2 - x1), slope):
                raise MathVisualValidationError("切线序列斜率与已验证斜率不一致")
            if not self._close(y1 + slope * (tangent_x - x1), tangent_y):
                raise MathVisualValidationError("切线序列未经过已验证切点")

        if visual_type == "area_under_curve":
            area = next((item for item in series if item["kind"] == "area"), None)
            if area is None:
                raise MathVisualValidationError("积分面积图必须包含 area 序列")
            lower = self._finite_number(request.get("lower"), "verification_request.lower")
            upper = self._finite_number(request.get("upper"), "verification_request.upper")
            xs = [point[0] for point in area["points"]]
            if not self._close(min(xs), min(lower, upper)) or not self._close(max(xs), max(lower, upper)):
                raise MathVisualValidationError("面积范围与已验证积分上下限不一致")

        return {"status": VERIFIED, "confidence": result.confidence, "checks": len(result.checks)}

    def _reconcile_annotations(
        self,
        annotations: Sequence[dict[str, Any]],
        series: Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        """点标注必须有采样证据；文字坐标可在证据一致时纠正模型位置。"""
        sampled = [point for item in series for point in item["points"]]
        cleaned: list[dict[str, Any]] = []
        partial = False
        for annotation in annotations:
            if annotation["kind"] != "point":
                cleaned.append(annotation)
                continue
            candidate = [annotation["x"], annotation["y"]]
            if self._point_is_sampled(candidate, sampled):
                cleaned.append(annotation)
                continue
            label_match = _LABELED_POINT.search(annotation.get("label", ""))
            if label_match:
                labeled = [float(label_match.group(1)), float(label_match.group(2))]
                if self._point_is_sampled(labeled, sampled):
                    fixed = dict(annotation)
                    fixed["x"], fixed["y"] = labeled
                    cleaned.append(fixed)
                    partial = True
                    continue
            # 无采样证据的点不进入渲染层，避免文字正确但位置错误的幻觉标注。
            partial = True
        return cleaned, partial

    @classmethod
    def _point_is_sampled(cls, candidate: Sequence[float], sampled: Sequence[Sequence[float]]) -> bool:
        return any(cls._close(candidate[0], point[0]) and cls._close(candidate[1], point[1]) for point in sampled)

    @staticmethod
    def _finite_number(raw: Any, path: str) -> float:
        if isinstance(raw, bool):
            raise MathVisualValidationError(f"{path} 必须是数字")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise MathVisualValidationError(f"{path} 必须是数字") from exc
        if not math.isfinite(value):
            raise MathVisualValidationError(f"{path} 必须是有限数")
        return value

    @staticmethod
    def _clean_text(raw: Any, path: str, *, required: bool = False) -> str:
        value = str(raw or "").strip()
        if required and not value:
            raise MathVisualValidationError(f"{path} 不能为空")
        if len(value) > MAX_TEXT_LENGTH:
            raise MathVisualValidationError(f"{path} 过长")
        if _EXECUTABLE_TEXT.search(value) or "<" in value or ">" in value:
            raise MathVisualValidationError(f"{path} 包含不可执行内容")
        return value

    @staticmethod
    def _close(left: float, right: float) -> bool:
        return math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6)


def mock_visual_spec(kind: str = "function_plot") -> dict[str, Any]:
    """返回固定 fixture；mock provider 与测试共用，不读取模型输出。"""
    if kind == "function_plot":
        points = [[x / 2, (x / 2) ** 2] for x in range(-6, 7)]
        return {
            "type": kind,
            "title": "y=x²",
            "viewport": {"x_min": -3, "x_max": 3, "y_min": -1, "y_max": 9},
            "series": [{"kind": "curve", "label": "y=x²", "points": points}],
            "annotations": [{"kind": "point", "x": 0, "y": 0, "label": "顶点"}],
            "teaching_note": "曲线关于 y 轴对称，并在原点取得最小值。",
        }
    if kind == "tangent_line":
        spec = mock_visual_spec("function_plot")
        spec.update(
            {
                "type": kind,
                "title": "y=x² 在 x=1 处的切线",
                "viewport": {"x_min": -3, "x_max": 3, "y_min": -7, "y_max": 9},
                "series": spec["series"]
                + [{"kind": "line", "label": "y=2x-1", "points": [[-3, -7], [3, 5]]}],
                "annotations": [{"kind": "point", "x": 1, "y": 1, "label": "切点 (1, 1)"}],
                "verification_request": {
                    "type": "derivative",
                    "expression": "x**2",
                    "derivative": "2*x",
                    "variable": "x",
                },
                "verified_values": {"tangent_x": 1, "tangent_y": 1, "slope": 2},
            }
        )
        return spec
    raise MathVisualValidationError(f"没有该 mock fixture：{kind}")


_visualizer: MathVisualizer | None = None


def get_math_visualizer() -> MathVisualizer:
    global _visualizer
    if _visualizer is None:
        _visualizer = MathVisualizer()
    return _visualizer
