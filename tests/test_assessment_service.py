import pytest
import yaml
from pathlib import Path
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Chapter, Course, ErrorItem, KnowledgeGraphVersion, KnowledgePoint, LearningRecord, Question, QuestionKnowledgePoint, User
from app.services.assessment_service import AssessmentBlueprintPlanner, create_assessment, get_assessment, quota_counts, save_draft, start_assessment, submit_assessment
from app.services.practice_service import PracticeError


class StubPlanner:
    async def plan(self, signals, inventory, question_count):
        return {"plan":{"buckets":[{"quota_kind":"weakness","knowledge_point_code":"limit","count":question_count,"difficulty_min":1,"difficulty_max":5,"reason_code":"weak_mastery","reason":"画像显示该知识点需要复测"}]},"source":"llm","model":"stub-deepseek","latency_ms":10,"token_usage":{"total_tokens":10},"error_code":None}


@pytest.mark.asyncio
async def test_assessment_uses_bank_persists_drafts_and_isolates_owner(monkeypatch):
    engine=create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine,"connect")
    def fk(connection,_): connection.execute("PRAGMA foreign_keys=ON")
    factory=async_sessionmaker(engine,expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database,"async_session_factory",factory)
    import app.services.assessment_service as service
    async def signals(user_id, points):
        return {"has_history":True,"skills":[{"code":"limit","mastery":0.2,"attempts":3}],"errors":[],"profile_weak_points":[{"label":"极限","mastery":0.2,"matched_codes":["limit"]}],"recent_summary":{"attempts":3,"correct":1}}
    monkeypatch.setattr(service,"_signals",signals)
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        course=Course(id="course-1",code="calculus",name="高等数学",subject="math",default_version_id="version-1")
        version=KnowledgeGraphVersion(id="version-1",course_id="course-1",version="1.0",name="V1",status="published")
        chapter=Chapter(id="chapter-1",course_id="course-1",version_id="version-1",code="c1",name="极限")
        point=KnowledgePoint(id="point-1",course_id="course-1",version_id="version-1",chapter_id="chapter-1",code="limit",name="极限")
        db.add_all([course,version,chapter,point,User(id="user-1",username="student",email="s@example.test",password_hash="x")]);await db.flush()
        for i in range(5):
            q=Question(id=f"A-{i}",content=f"检测题{i}",question_type="choice",options=[{"id":"A","text":"正确"}],answer="A",analysis="题库解析",category="高数",difficulty=2,course_id="course-1",version_id="version-1",review_status="published",grading_mode="deterministic",practice_eligible=True,exam_eligible=True,auto_grading_eligible=True,answer_spec={"kind":"choice","correct":"A"})
            db.add(q);await db.flush();db.add(QuestionKnowledgePoint(question_id=q.id,knowledge_point_id="point-1"))
        await db.commit()
    config={"goal":"weakness_check","course_id":"course-1","version_id":"version-1","scope":{"chapter_ids":["chapter-1"]},"duration_minutes":15,"intensity":"standard","question_count":5,"idempotency_key":"assessment-create-1","random_seed":7}
    session=await create_assessment("user-1",config,planner=StubPlanner())
    assert session["planning_source"]=="llm" and len(session["questions"])==5
    assert session["blueprint_schema_version"] == "2"
    assert session["quota_summary"] == {"weakness": 5, "due_review": 0, "current_chapter": 0, "challenge": 0}
    assert all("answer_spec" not in q and "analysis" not in q for q in session["questions"])
    with pytest.raises(PracticeError,match="不存在"): await get_assessment("other-user",session["session_id"])
    await start_assessment("user-1",session["session_id"])
    for index, q in enumerate(session["questions"]):
        await save_draft("user-1", session["session_id"], q["question_id"], "B" if index == 4 else "A", 0)
    result=await submit_assessment("user-1",session["session_id"],"submit-key")
    assert result["correct"]==4 and result["status"]=="completed"
    assert (await submit_assessment("user-1",session["session_id"],"submit-key"))["correct"]==4
    async with factory() as db:
        assert (await db.execute(select(func.count(LearningRecord.id)).where(LearningRecord.user_id=="user-1",LearningRecord.event_type=="assessment_answer"))).scalar_one()==5
        captured = (await db.execute(select(ErrorItem).where(ErrorItem.user_id == "user-1"))).scalar_one()
        assert len(captured.item_id) == 36
        assert len(captured.added_at) > 30
        assert ErrorItem.__table__.c.added_at.type.length == 64
    await engine.dispose()


@pytest.mark.asyncio
async def test_llm_question_content_is_rejected_and_rules_fallback(monkeypatch):
    import app.services.assessment_service as service
    monkeypatch.setattr(service,"is_assessment_ai_available",lambda:True)
    class Response:
        content='{"question_id":"Q-secret","buckets":[]}'
        model="deepseek-chat";latency_ms=5;usage={}
    class FakeLLM:
        async def generate(self,**kwargs): return Response()
    planner=AssessmentBlueprintPlanner(FakeLLM())
    planned=await planner.plan({"has_history":False,"skills":[],"errors":[],"profile_weak_points":[]},[{"knowledge_point_code":"limit","available":5}],5)
    assert planned["source"]=="rule_fallback"
    assert "question_id" not in str(planned["plan"])


def test_assessment_ai_availability_uses_deepseek_key(monkeypatch):
    import app.services.assessment_service as service
    monkeypatch.setattr(service.settings, "AI_ENABLED", True)
    monkeypatch.setattr(service.settings, "DASHSCOPE_API_KEY", "qwen-key")
    monkeypatch.setattr(service.settings, "DEEPSEEK_API_KEY", "")
    assert service.is_assessment_ai_available() is False
    monkeypatch.setattr(service.settings, "DEEPSEEK_API_KEY", "deepseek-key")
    assert service.is_assessment_ai_available() is True


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not-json", '{"buckets":[{"knowledge_point_code":"unknown","count":1,"difficulty_min":1,"difficulty_max":5,"reason_code":"coverage","reason":"x"}]}'])
async def test_assessment_planner_falls_back_for_malformed_or_inventory_conflict(monkeypatch, content):
    import app.services.assessment_service as service
    monkeypatch.setattr(service, "is_assessment_ai_available", lambda: True)
    class Response:
        model = "deepseek-chat"; latency_ms = 3; usage = {}
    class FakeLLM:
        async def generate(self, **kwargs):
            response = Response(); response.content = content; return response
    planned = await AssessmentBlueprintPlanner(FakeLLM()).plan(
        {"has_history": True, "skills": [], "errors": [], "profile_weak_points": [], "due_reviews": []},
        [{"knowledge_point_code": "limit", "available": 2}], 1,
    )
    assert planned["source"] == "rule_fallback"


@pytest.mark.asyncio
async def test_assessment_planner_falls_back_on_timeout(monkeypatch):
    import app.services.assessment_service as service
    monkeypatch.setattr(service, "is_assessment_ai_available", lambda: True)
    class FakeLLM:
        async def generate(self, **kwargs): raise TimeoutError("provider timeout")
    planned = await AssessmentBlueprintPlanner(FakeLLM()).plan(
        {"has_history": True, "skills": [], "errors": [], "profile_weak_points": [], "due_reviews": []},
        [{"knowledge_point_code": "limit", "available": 2}], 1,
    )
    assert planned["source"] == "rule_fallback" and planned["error_code"] == "TimeoutError"


def test_rule_plan_prioritizes_due_review():
    plan = AssessmentBlueprintPlanner.rule_plan(
        {"skills": [], "errors": [], "profile_weak_points": [], "due_reviews": [{"code": "limit"}]},
        [{"knowledge_point_code": "limit", "available": 2}, {"knowledge_point_code": "continuity", "available": 2}], 1,
    )
    assert plan.buckets[0].knowledge_point_code == "limit"
    assert plan.buckets[0].quota_kind == "due_review"
    assert plan.buckets[0].reason_code == "review_due"


@pytest.mark.asyncio
async def test_assessment_planner_requests_deepseek_model(monkeypatch):
    import app.services.assessment_service as service
    monkeypatch.setattr(service, "is_assessment_ai_available", lambda: True)
    monkeypatch.setattr(service.settings, "DEEPSEEK_MODEL", "deepseek-chat")
    captured = {}

    class Response:
        content = '{"buckets":[{"quota_kind":"weakness","knowledge_point_code":"limit","count":1,"difficulty_min":1,"difficulty_max":5,"reason_code":"coverage","reason":"范围覆盖"}]}'
        model = "deepseek-chat"
        latency_ms = 5
        usage = {}

    class FakeLLM:
        async def generate(self, **kwargs):
            captured.update(kwargs)
            return Response()

    planned = await AssessmentBlueprintPlanner(FakeLLM()).plan(
        {"has_history": False, "skills": [], "errors": [], "profile_weak_points": []},
        [{"knowledge_point_code": "limit", "available": 1}],
        1,
    )
    assert planned["source"] == "llm"
    assert captured["model"] == "deepseek-chat"
    assert "question_id" not in captured["prompt"]


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("weakness_check", {"weakness": 5, "due_review": 2, "current_chapter": 2, "challenge": 1}),
        ("stage_retest", {"weakness": 4, "due_review": 3, "current_chapter": 2, "challenge": 1}),
        ("review_due", {"weakness": 3, "due_review": 5, "current_chapter": 1, "challenge": 1}),
        ("comprehensive", {"weakness": 3, "due_review": 3, "current_chapter": 3, "challenge": 1}),
    ],
)
def test_v2_quota_presets_use_largest_remainder(goal, expected):
    assert quota_counts(goal, 10) == expected


def test_assessment_blueprint_evaluation_matrix_is_versioned_and_synthetic():
    matrix = yaml.safe_load(Path("evaluations/assessment_blueprint_v2.yaml").read_text(encoding="utf-8"))
    assert matrix["schema_version"] == "2"
    assert matrix["fact_source"] == "synthetic-only"
    assert len(matrix["cases"]) == 10


@pytest.mark.asyncio
async def test_planner_rejects_quota_conflict_and_challenge_below_level_four(monkeypatch):
    import app.services.assessment_service as service
    monkeypatch.setattr(service, "is_assessment_ai_available", lambda: True)

    class Response:
        model = "deepseek-chat"; latency_ms = 2; usage = {}

    class FakeLLM:
        async def generate(self, **kwargs):
            response = Response()
            response.content = '{"buckets":[{"quota_kind":"challenge","knowledge_point_code":"limit","count":1,"difficulty_min":1,"difficulty_max":5,"reason_code":"challenge","reason":"挑战"}]}'
            return response

    planned = await AssessmentBlueprintPlanner(FakeLLM()).plan(
        {"has_history": True, "skills": [{"code": "limit", "mastery": 0.8}], "errors": [], "profile_weak_points": [], "due_reviews": [], "assessment_request": {"goal": "comprehensive"}},
        [{"knowledge_point_code": "limit", "available": 2, "available_difficulty": {"4": 2}}], 1,
    )
    assert planned["source"] == "rule_fallback"
