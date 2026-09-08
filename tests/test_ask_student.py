"""
T03 ask_student 结构化反问工具测试。

覆盖验收清单：
- 缺条件题目触发澄清（工具创建 pending 澄清记录）
- 两个会话交叉回复时不串线（断言拒绝）
- mock 模式自动空回复不挂起（auto_resolved，不创建 pending）
- 每轮最多 1 次调用（同会话第二次调用被拒绝）
- 语义续接消息包含"你刚才问了 X，学生答 Y"
"""

import pytest

from app.config.settings import settings
from app.services.clarification_store import (
    ClarificationMismatchError,
    build_continuation_message,
    get_clarification_store,
)
from tools.ask_student_tool import AskStudentTool
from tools.base_tool import ToolInput


def _make_input(
    question: str = "已知三角形两边长，求第三边，还缺什么条件？",
    kind: str = "missing_condition",
    user_id: str = "user-1",
    session_id: str = "session-1",
    **extra_params,
) -> ToolInput:
    params = {"question": question, "kind": kind}
    params.update(extra_params)
    return ToolInput(
        query=question,
        parameters=params,
        context={"user_id": user_id, "session_id": session_id, "source": "test"},
    )


@pytest.fixture(autouse=True)
def _clean_store():
    get_clarification_store().reset()
    yield
    get_clarification_store().reset()


# ── 工具基本行为 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_condition_creates_pending_clarification():
    """缺条件题目触发澄清：工具创建 pending 澄清并返回四重标识。"""
    tool = AskStudentTool()
    output = await tool.execute(
        _make_input(
            options=[{"label": "A", "text": "是直角三角形"}, {"label": "B", "text": "给出夹角"}]
        )
    )

    assert output.success
    data = output.data
    assert data["clarification_id"]
    assert data["pending_turn_id"]
    assert data["session_id"] == "session-1"
    assert data["kind"] == "missing_condition"
    assert data["question_summary"]
    assert len(data["options"]) == 2

    pending = await get_clarification_store().get_pending("user-1", "session-1")
    assert pending is not None
    assert pending.clarification_id == data["clarification_id"]
    assert pending.pending_turn_id == data["pending_turn_id"]


@pytest.mark.asyncio
async def test_invalid_kind_rejected():
    """kind 只允许 3 种枚举，其他值拒绝。"""
    output = await AskStudentTool().execute(_make_input(kind="ask_answer"))
    assert not output.success
    assert "kind" in (output.error or "")


@pytest.mark.asyncio
async def test_empty_question_rejected():
    output = await AskStudentTool().execute(_make_input(question=""))
    assert not output.success


@pytest.mark.asyncio
async def test_missing_user_context_rejected():
    """数据按真实 user_id 隔离：缺身份上下文直接拒绝。"""
    tool = AskStudentTool()
    bad = ToolInput(query="问题", parameters={"question": "问题"}, context={})
    output = await tool.execute(bad)
    assert not output.success
    assert "user_id" in (output.error or "")


# ── 每轮最多 1 次 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_second_call_in_same_turn_refused():
    """同一会话已有 pending 澄清时，第二次调用被拒绝且不创建新记录。"""
    tool = AskStudentTool()
    first = await tool.execute(_make_input())

    second = await tool.execute(_make_input(question="第二个澄清问题"))
    assert second.success
    assert second.data.get("duplicate") is True
    assert "clarification_id" not in second.data

    pending = await get_clarification_store().get_pending("user-1", "session-1")
    assert pending is not None
    assert pending.clarification_id == first.data["clarification_id"]


@pytest.mark.asyncio
async def test_can_ask_again_after_resolve():
    """澄清被回答（resolved）后，新一轮可以再次提问。"""
    tool = AskStudentTool()
    first = await tool.execute(_make_input())
    await get_clarification_store().resolve(
        user_id="user-1",
        session_id="session-1",
        clarification_id=first.data["clarification_id"],
        pending_turn_id=first.data["pending_turn_id"],
        answer="是直角三角形",
    )

    second = await tool.execute(_make_input(question="还有别的解法吗？"))
    assert second.success
    assert second.data.get("duplicate") is not True
    assert second.data["clarification_id"] != first.data["clarification_id"]


# ── mock / headless 自动解决（批处理不挂起） ─────────────────────────


@pytest.mark.asyncio
async def test_mock_provider_auto_resolves_without_pending(monkeypatch):
    """CONTENT_AI_PROVIDER=mock 时自动返回空回复并附 auto_resolved: true。"""
    monkeypatch.setattr(settings, "CONTENT_AI_PROVIDER", "mock")
    output = await AskStudentTool().execute(_make_input())

    assert output.success
    assert output.data.get("auto_resolved") is True
    assert "clarification_id" not in output.data
    # 不创建 pending 记录，批处理不挂起
    assert await get_clarification_store().get_pending("user-1", "session-1") is None


@pytest.mark.asyncio
async def test_batch_context_flag_auto_resolves(monkeypatch):
    """显式 headless/batch_mode 上下文标记同样自动解决（评测跑批场景）。"""
    monkeypatch.setattr(settings, "CONTENT_AI_PROVIDER", "deepseek")
    tool = AskStudentTool()
    bad = ToolInput(
        query="问题",
        parameters={"question": "问题"},
        context={"user_id": "user-1", "session_id": "session-1", "batch_mode": True},
    )
    output = await tool.execute(bad)
    assert output.success
    assert output.data.get("auto_resolved") is True


# ── 会话串线防护（clarification_id / pending_turn_id / session_id / user_id） ──


@pytest.mark.asyncio
async def test_cross_session_reply_rejected():
    """构造两个会话交叉回复，断言拒绝续接。"""
    tool = AskStudentTool()
    output = await tool.execute(_make_input(user_id="user-1", session_id="session-1"))
    store = get_clarification_store()

    with pytest.raises(ClarificationMismatchError):
        await store.resolve(
            user_id="user-1",
            session_id="session-2",  # 会话不匹配
            clarification_id=output.data["clarification_id"],
            pending_turn_id=output.data["pending_turn_id"],
            answer="是直角三角形",
        )


@pytest.mark.asyncio
async def test_cross_user_reply_rejected():
    """user_id 不匹配（跨用户串线）拒绝续接。"""
    tool = AskStudentTool()
    output = await tool.execute(_make_input(user_id="user-1", session_id="session-1"))
    store = get_clarification_store()

    with pytest.raises(ClarificationMismatchError):
        await store.resolve(
            user_id="user-2",
            session_id="session-1",
            clarification_id=output.data["clarification_id"],
            pending_turn_id=output.data["pending_turn_id"],
            answer="是直角三角形",
        )


@pytest.mark.asyncio
async def test_wrong_pending_turn_id_rejected():
    """pending_turn_id 不匹配拒绝续接。"""
    tool = AskStudentTool()
    output = await tool.execute(_make_input())
    store = get_clarification_store()

    with pytest.raises(ClarificationMismatchError):
        await store.resolve(
            user_id="user-1",
            session_id="session-1",
            clarification_id=output.data["clarification_id"],
            pending_turn_id="deadbeef" * 8,
            answer="是直角三角形",
        )


@pytest.mark.asyncio
async def test_unknown_clarification_id_rejected():
    store = get_clarification_store()
    with pytest.raises(ClarificationMismatchError):
        await store.resolve(
            user_id="user-1",
            session_id="session-1",
            clarification_id="nonexistent",
            pending_turn_id="nonexistent",
            answer="答案",
        )


@pytest.mark.asyncio
async def test_double_submit_rejected():
    """重复提交（幂等防护）：已 resolved 的澄清再次 resolve 拒绝。"""
    tool = AskStudentTool()
    output = await tool.execute(_make_input())
    store = get_clarification_store()

    record = await store.resolve(
        user_id="user-1",
        session_id="session-1",
        clarification_id=output.data["clarification_id"],
        pending_turn_id=output.data["pending_turn_id"],
        answer="是直角三角形",
    )
    assert record.status == "resolved"
    assert record.answer == "是直角三角形"

    with pytest.raises(ClarificationMismatchError):
        await store.resolve(
            user_id="user-1",
            session_id="session-1",
            clarification_id=output.data["clarification_id"],
            pending_turn_id=output.data["pending_turn_id"],
            answer="再答一次",
        )


@pytest.mark.asyncio
async def test_abandon_releases_pending():
    """学生忽略卡片直接发新消息时 abandon 释放占用，后续可再次反问。"""
    tool = AskStudentTool()
    await tool.execute(_make_input())
    store = get_clarification_store()
    await store.abandon("user-1", "session-1")
    assert await store.get_pending("user-1", "session-1") is None

    again = await tool.execute(_make_input(question="重新提问"))
    assert again.success
    assert again.data.get("duplicate") is not True


# ── 语义续接消息 ────────────────────────────────────────────────────


def test_continuation_message_mentions_question_and_answer():
    """续接消息显式包含"你刚才问了 X / 学生答 Y"，供模型引用学生回答继续推理。"""
    message = build_continuation_message("还缺什么条件？", "是直角三角形")
    assert "你刚才问了学生" in message
    assert "还缺什么条件" in message
    assert "是直角三角形" in message


def test_question_summary_truncated():
    long_question = "长" * 300
    from app.services.clarification_store import build_question_summary
    summary = build_question_summary(long_question)
    assert len(summary) <= 122  # 120 + 省略号
    assert summary.endswith("…")


# ── HTTP 层：澄清回答端点 409 校验 ───────────────────────────────────


@pytest.fixture
def api_client():
    """带认证 mock 的 TestClient（对齐 test_api_integration.py 的做法）。"""
    from unittest.mock import Mock, AsyncMock, patch, MagicMock

    mock_user = MagicMock()
    mock_user.id = "user-1"
    mock_user.is_active = True
    mock_user.role = "student"

    with patch("app.dependencies._llm_service", Mock()), \
         patch("app.dependencies._vector_store", Mock()), \
         patch("main.agent", Mock()), \
         patch("main.registry", Mock()), \
         patch("main.error_book_manager", MagicMock()), \
         patch("app.middleware.auth_middleware.get_user_by_id", AsyncMock(return_value=mock_user)):
        from main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as _:
            pass  # 不触发 lifespan，仅构造客户端
        client = TestClient(app)
        yield client


def _auth_headers() -> dict:
    from app.middleware.auth import create_access_token
    from app.config.settings import settings
    token = create_access_token(
        "user-1", settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM
    )
    return {"Authorization": f"Bearer {token}"}


def _run(coro):
    """在同步测试中执行 store 协程（store 为纯内存实现，与事件循环无关）。"""
    import asyncio
    return asyncio.run(coro)


def test_clarification_answer_cross_session_rejected_with_409(api_client):
    """HTTP 层验证会话串线：session 不匹配返回 409 CLARIFICATION_MISMATCH。"""
    store = get_clarification_store()
    record = _run(store.create(user_id="user-1", session_id="session-1", question="还缺什么条件？"))

    response = api_client.post(
        "/api/chat/clarification/answer",
        headers=_auth_headers(),
        json={
            "session_id": "session-2",  # 串线：与创建时的会话不一致
            "clarification_id": record.clarification_id,
            "pending_turn_id": record.pending_turn_id,
            "answer": "是直角三角形",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CLARIFICATION_MISMATCH"
    # 拒绝续接后要求重新提问：原 pending 仍在，可被重新回答
    pending = _run(store.get_pending("user-1", "session-1"))
    assert pending is not None
    assert pending.clarification_id == record.clarification_id


# ── SSE 层：ask_student 事件下发 ────────────────────────────────────


class _StubAgent:
    """模拟 Agent：stream 期间创建一条 pending 澄清，然后输出文本。"""

    def __init__(self, user_id: str, session_id: str):
        self._user_id = user_id
        self._session_id = session_id

    async def stream(self, message, session_id=None, user_id=None, **kwargs):
        await get_clarification_store().create(
            user_id=user_id,
            session_id=session_id,
            question="已知三角形两边长，求第三边，缺什么条件？",
            options=[{"label": "A", "text": "是直角三角形"}],
            kind="missing_condition",
        )
        yield "请补充条件后我继续推理。"


@pytest.mark.asyncio
async def test_stream_emits_ask_student_event():
    """SSE 流在本轮创建 pending 澄清后下发 ask_student 事件（携带四重标识）。"""
    import json
    from app.services.stream_handler import stream_agent_response

    events = []
    async for chunk in stream_agent_response(
        _StubAgent("user-1", "session-1"),
        "已知两边求第三边",
        "session-1",
        user_id="user-1",
    ):
        events.append(chunk)

    text = "".join(events)
    assert "event: ask_student" in text
    data_line = next(
        line for line in text.splitlines() if line.startswith("data: {") and "clarification_id" in line
    )
    payload = json.loads(data_line[len("data: "):])
    assert payload["type"] == "ask_student"
    assert payload["clarification_id"]
    assert payload["pending_turn_id"]
    assert payload["session_id"] == "session-1"
    assert payload["question"].startswith("已知三角形两边长")
    # 澄清事件后直接收尾（done），不再追加推荐
    assert "'type': 'done'" in text or '"type": "done"' in text
