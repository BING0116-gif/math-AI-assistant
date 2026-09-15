from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.data.database as database
from app.config.settings import settings
from app.data.models import AnimationJob, Base, User
from app.services.animation_service import trusted_animation_visual_spec, validate_public_animation_request
from tools.base_tool import ToolInput
from tools.math_animate_tool import MathAnimateTool, animation_teaching_decision
from app.services.stream_handler import stream_agent_response


@pytest.mark.parametrize(
    ("question", "template_id", "visual_type", "admitted", "trigger"),
    [
        ("请用动画演示割线如何趋近切线", "secant_to_tangent", "tangent_line", True, "user_explicit"),
        ("导数为什么等于切线斜率？", "secant_to_tangent", "tangent_line", True, "teaching_strategy"),
        ("黎曼和怎样趋近定积分？", "riemann_sum", "area_under_curve", True, "teaching_strategy"),
        ("解方程 x+2=5", "secant_to_tangent", "tangent_line", False, "teaching_strategy"),
        ("解释泰勒公式", "secant_to_tangent", "tangent_line", False, "teaching_strategy"),
        ("导数是什么", "riemann_sum", "area_under_curve", False, "teaching_strategy"),
        ("请画图解释积分", "riemann_sum", "tangent_line", False, "teaching_strategy"),
    ],
)
def test_animation_teaching_policy_matrix(question, template_id, visual_type, admitted, trigger):
    decision = animation_teaching_decision(question, template_id, visual_type)
    assert decision["admitted"] is admitted
    assert decision["trigger"] == trigger


@pytest.mark.asyncio
async def test_disabled_tool_falls_back_before_validation_or_database(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", False)
    output = await MathAnimateTool().execute(ToolInput(
        query="解释割线趋近切线",
        parameters={"parameters": {
            "template_id": "secant_to_tangent",
        }},
        context={"user_id": "owner-a", "session_id": "chat-a", "original_user_input": "请用动画演示导数"},
    ))
    assert output.success is True
    assert output.data["animation_status"] == "static_fallback"


@pytest.mark.asyncio
async def test_irrelevant_question_is_rejected_even_if_model_calls_tool(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", True)
    output = await MathAnimateTool().execute(ToolInput(
        query="做一个动画",
        parameters={"parameters": {
            "template_id": "secant_to_tangent",
        }},
        context={"user_id": "owner-a", "session_id": "chat-a", "original_user_input": "解方程 x+2=5"},
    ))
    assert output.success is True
    assert output.data["animation_status"] == "static_fallback"
    assert output.data["decision"]["admitted"] is False


@pytest.mark.asyncio
async def test_admitted_agent_tool_enqueues_owner_scoped_job(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", True)
    monkeypatch.setattr(settings, "ANIMATION_RENDERER_IMAGE", "sha256:" + "c" * 64)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id="owner-a", username="anim-owner", email="anim-owner@example.test", password_hash="x"))
        await db.commit()

    animations = []
    output = await MathAnimateTool().execute(ToolInput(
        query="观察割线斜率逐步趋近切线斜率",
        parameters={"parameters": {
            "template_id": "secant_to_tangent",
        }},
        context={
            "user_id": "owner-a", "session_id": "chat-a",
            "original_user_input": "导数为什么等于切线斜率？", "animations": animations,
        },
    ))
    assert output.success is True
    assert output.data["status"] == "pending"
    assert animations[0]["job_id"] == output.data["job_id"]
    assert "user_id" not in output.data
    async with factory() as db:
        job = await db.get(AnimationJob, output.data["job_id"])
        assert job.user_id == "owner-a"
        assert job.trigger == "teaching_strategy"
    await engine.dispose()


def test_tool_contract_does_not_accept_identity_or_runtime_controls():
    schema = MathAnimateTool().get_info()["input_schema"]
    encoded = str(schema)
    for forbidden in ("user_id", "worker_id", "renderer_image", "python_code", "docker"):
        assert forbidden not in encoded


@pytest.mark.parametrize("template_id", ["secant_to_tangent", "riemann_sum"])
def test_server_owned_template_specs_pass_t08_and_fixed_template_admission(template_id):
    spec = trusted_animation_visual_spec(template_id)
    admission, source_hash = validate_public_animation_request(
        template_id=template_id, visual_spec=spec,
    )
    assert admission["verified"] is True
    assert len(source_hash) == 64


@pytest.mark.asyncio
async def test_animation_job_is_emitted_after_text_explanation():
    class FakeAgent:
        _last_run_metadata = {"animations": [{
            "job_id": "job-1", "status": "pending", "stage": "queued",
            "template_id": "secant_to_tangent", "attempt_count": 0,
            "created_at": "2026-09-14T00:00:00Z", "updated_at": "2026-09-14T00:00:00Z",
            "artifacts": [], "teaching_note": "观察割线趋近切线",
        }]}

        async def stream(self, *args, **kwargs):
            yield "先看割线斜率如何变化。"

    body = "".join([
        chunk async for chunk in stream_agent_response(
            FakeAgent(), "解释导数", "session-1", user_id="student-1", tutor_mode="tutor_free"
        )
    ])
    first_payload = body.split("\n\n", 1)[0]
    assert json.loads(first_payload.removeprefix("data: "))["content"] == "先看割线斜率如何变化。"
    assert body.index("data: ") < body.index("event: animation_job")
    assert '"job_id": "job-1"' in body
    assert '"type": "done"' in body


def test_builtin_registry_exposes_math_animate():
    import tools

    tools._registry = None
    try:
        assert tools.get_registry().get_tool("math_animate").name == "math_animate"
    finally:
        tools._registry = None
