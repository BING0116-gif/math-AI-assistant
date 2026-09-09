"""T08 MathVisualizer 的安全、验证联动与 SSE 降级回归测试。"""

import json

import pytest

from app.services.math_visualizer import (
    MAX_POINTS_PER_SERIES,
    MathVisualValidationError,
    MathVisualizer,
    mock_visual_spec,
)
from app.services.stream_handler import stream_agent_response
from agent_core.langchain_adapter import LangChainToolConverter
from tools import get_registry
from tools.base_tool import ToolInput
from tools.math_visualize_tool import MathVisualizeTool


def test_function_plot_fixture_is_deterministic_and_renderable():
    visualizer = MathVisualizer()
    assert mock_visual_spec() == mock_visual_spec()
    result = visualizer.visualize(mock_visual_spec())
    assert result["visualization_status"] == "ok"
    assert result["spec"]["type"] == "function_plot"
    assert result["spec"]["series"][0]["points"][6] == [0.0, 0.0]
    assert result["verification"] is None


@pytest.mark.parametrize(
    ("visual_type", "series", "extra"),
    [
        ("function_plot", [{"kind": "curve", "label": "f", "points": [[-1, 1], [0, 0], [1, 1]]}], {}),
        ("tangent_line", mock_visual_spec("tangent_line")["series"], {
            "verification_request": mock_visual_spec("tangent_line")["verification_request"],
            "verified_values": {"tangent_x": 1, "tangent_y": 1, "slope": 2},
        }),
        ("area_under_curve", [
            {"kind": "curve", "label": "y=x", "points": [[0, 0], [1, 1], [2, 2]]},
            {"kind": "area", "label": "积分面积", "points": [[0, 0], [1, 1], [2, 2], [2, 0], [0, 0]]},
        ], {"verification_request": {"type": "integral", "expression": "x", "lower": 0, "upper": 2, "claimed": 2}}),
        ("vector_plot", [{"kind": "vector", "label": "v", "points": [[0, 0], [2, 3]]}], {}),
        ("sequence_plot", [{"kind": "sequence", "label": "aₙ", "points": [[1, 1], [2, 0.5], [3, 0.333]]}], {}),
        ("geometry_plot", [{"kind": "polygon", "label": "三角形", "points": [[0, 0], [2, 0], [1, 2], [0, 0]]}], {}),
    ],
)
def test_all_six_visual_types_have_valid_contracts(visual_type, series, extra):
    spec = {
        "type": visual_type,
        "title": visual_type,
        "viewport": {"x_min": -3, "x_max": 3, "y_min": -7, "y_max": 9},
        "series": series,
        "annotations": [],
        "teaching_note": "fixture",
        **extra,
    }
    result = MathVisualizer().visualize(spec)
    assert result["visualization_status"] == "ok"
    assert result["spec"]["type"] == visual_type


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda spec: spec.update(type="unknown"), "不支持"),
        (lambda spec: spec["series"][0].update(points=[[0, 0]] * (MAX_POINTS_PER_SERIES + 1)), "点数"),
        (lambda spec: spec["series"][0]["points"].append([float("nan"), 0]), "有限数"),
        (lambda spec: spec["series"][0]["points"].append([0, float("inf")]), "有限数"),
        (lambda spec: spec["series"][0]["points"].append([2_000_000, 0]), "全局范围"),
        (lambda spec: spec.update(title="<script>alert(1)</script>"), "不可执行"),
        (lambda spec: spec["series"][0].update(kind="foreignObject"), "白名单"),
    ],
)
def test_invalid_or_executable_spec_is_rejected(mutate, message):
    spec = mock_visual_spec()
    mutate(spec)
    with pytest.raises(MathVisualValidationError, match=message):
        MathVisualizer().visualize(spec)


def test_points_outside_viewport_are_clipped_and_marked_partial():
    spec = mock_visual_spec()
    spec["series"][0]["points"] = [[-4, 16], [0, 0], [4, 16]]
    result = MathVisualizer().visualize(spec)
    assert result["visualization_status"] == "partial"
    assert result["spec"]["series"][0]["points"] == [[-3.0, 9.0], [0.0, 0.0], [3.0, 9.0]]


def test_point_annotation_is_corrected_only_when_label_has_sampled_evidence():
    spec = mock_visual_spec()
    spec["annotations"] = [
        {"kind": "point", "x": 0.5, "y": -0.6, "label": "顶点 (0,0)"},
        {"kind": "point", "x": 0.5, "y": 0.5, "label": "不存在的点"},
    ]
    result = MathVisualizer().visualize(spec)
    assert result["visualization_status"] == "partial"
    assert result["spec"]["annotations"] == [{"kind": "point", "label": "顶点 (0,0)", "x": 0.0, "y": 0.0}]


def test_tangent_line_uses_verified_derivative_point_and_slope():
    result = MathVisualizer().visualize(mock_visual_spec("tangent_line"))
    assert result["verification"]["status"] == "verified"
    assert result["spec"]["series"][1]["points"] == [[-3.0, -7.0], [3.0, 5.0]]


def test_tangent_line_mismatch_is_rejected():
    spec = mock_visual_spec("tangent_line")
    spec["verified_values"]["slope"] = 3
    with pytest.raises(MathVisualValidationError, match="切点或斜率"):
        MathVisualizer().visualize(spec)


@pytest.mark.asyncio
async def test_tool_collects_pure_visual_data_for_sse():
    collected = []
    output = await MathVisualizeTool().execute(
        ToolInput(
            query="画出 y=x^2",
            parameters={"spec": mock_visual_spec()},
            context={"visualizations": collected},
        )
    )
    assert output.success is True
    assert output.data["visualization_status"] == "ok"
    assert collected == [output.data]
    assert "<script" not in output.result.lower()


@pytest.mark.asyncio
async def test_langchain_tool_exposes_and_accepts_full_visual_schema():
    tool = LangChainToolConverter().convert(MathVisualizeTool())
    output = await tool.ainvoke({"query": "画出 y=x²", "parameters": {"spec": mock_visual_spec()}})
    payload = json.loads(output)
    assert payload["visualization_status"] == "ok"
    schema = tool.args_schema.model_json_schema()
    assert "MathVisualSpecInput" in schema["$defs"]


@pytest.mark.asyncio
async def test_visualizer_failure_does_not_block_text_reply():
    class FakeAgent:
        _last_run_metadata = {
            "visualizations": [
                {"visualization_status": "failed", "spec": None, "message": "invalid spec"}
            ]
        }

        async def stream(self, *args, **kwargs):
            yield "文字解答仍然完成"

    chunks = [
        chunk
        async for chunk in stream_agent_response(
            FakeAgent(), "画图", "session-1", user_id="student-1", tutor_mode="tutor_free"
        )
    ]
    body = "".join(chunks)
    first_payload = json.loads(body.split("\n\n", 1)[0].removeprefix("data: "))
    assert first_payload["content"] == "文字解答仍然完成"
    assert "event: visualization" in body
    assert '"visualization_status": "failed"' in body
    assert '"type": "done"' in body


def test_builtin_registry_exposes_math_visualize():
    import tools

    tools._registry = None
    try:
        assert get_registry().get_tool("math_visualize").name == "math_visualize"
    finally:
        tools._registry = None
