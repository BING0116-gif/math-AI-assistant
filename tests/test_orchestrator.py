"""T10 Capability + Orchestrator 分层回归测试。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from agent_core.capabilities.diagnose_error import DiagnoseErrorCapability
from agent_core.capabilities.solve import SolveCapability
from agent_core.langchain_adapter import LangChainToolConverter
from agent_core.orchestrator import MathOrchestrator
from app.services.stream_handler import stream_agent_response
from tools.base_tool import BaseTool, ToolInput, ToolOutput


@pytest.mark.asyncio
async def test_routes_review_mode_to_diagnose_and_reuses_legacy_strategy():
    """review + 学生步骤应路由诊错，但执行对象必须是原策略选择器返回的对象。"""
    legacy_strategy = object()
    selector = AsyncMock(return_value=legacy_strategy)
    orchestrator = MathOrchestrator(selector)
    context = {"tutor_mode": "review"}

    route = await orchestrator.route("我的推导哪里错了？", "student-1:session-1", context)

    assert route.manifest.name == "diagnose_error"
    assert route.strategy is legacy_strategy
    selector.assert_awaited_once_with("我的推导哪里错了？", "student-1:session-1")
    assert context["capability"] == "diagnose_error"
    assert "error_book_analysis" in context["capability_allowed_tools"]


@pytest.mark.asyncio
async def test_routes_general_question_to_solve_and_keeps_existing_strategy_path():
    legacy_strategy = object()
    selector = AsyncMock(return_value=legacy_strategy)
    orchestrator = MathOrchestrator(selector)
    context = {"tutor_mode": "guided"}

    route = await orchestrator.route("求极限 lim(x→0) sin(x)/x", "student-1:session-1", context)

    assert route.manifest.name == "solve"
    assert route.strategy is legacy_strategy
    assert context["capability_strategy_policy"] == "existing_complexity_strategy"


def test_capability_tool_sets_are_independent_and_mode_is_an_additional_boundary():
    solve = SolveCapability().manifest
    diagnose = DiagnoseErrorCapability().manifest

    assert "recommend_questions" in solve.allowed_tools
    assert "recommend_questions" not in diagnose.allowed_tools
    assert "error_book_analysis" in diagnose.allowed_tools
    assert "error_book_analysis" not in solve.allowed_tools
    assert "hint_only" not in diagnose.supported_modes


class _DisallowedTool(BaseTool):
    """验证 Capability 边界不能仅依赖给模型看的工具列表。"""

    name = "explain_question"
    description = "test"

    def __init__(self):
        self.called = False

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        self.called = True
        return ToolOutput(success=True, result="should not run", tool_name=self.name)


@pytest.mark.asyncio
async def test_capability_boundary_blocks_tool_execution_even_in_free_mode():
    tool_impl = _DisallowedTool()
    converter = LangChainToolConverter()
    converter.set_context({
        "tutor_mode": "tutor_free",
        "capability_allowed_tools": frozenset({"math_verify"}),
    })

    output = await converter.convert(tool_impl).ainvoke({"query": "请解释"})

    assert output.startswith("[MODE_TOOL_DENIED]")
    assert tool_impl.called is False


@pytest.mark.asyncio
async def test_existing_sse_text_and_done_contract_remain_unchanged():
    """编排元数据是内部审计信息，旧 SSE 消费端仍只接收 content/done。"""

    class FakeAgent:
        _follow_up_text = None
        _last_run_metadata = {"capability": "solve"}

        async def stream(self, *args, **kwargs):
            yield "旧文本事件"

    payload = "".join([
        chunk async for chunk in stream_agent_response(
            FakeAgent(), "求导", "session-1", user_id="student-1", tutor_mode="guided", tutor_context={}
        )
    ])

    events = [
        json.loads(line.removeprefix("data: "))
        for line in payload.splitlines()
        if line.startswith("data: ")
    ]
    assert events == [
        {"content": "旧文本事件", "type": "content"},
        {"content": "", "type": "done"},
    ]
    assert "capability" not in payload
