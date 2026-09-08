import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, Chapter, Course, ErrorItem, KnowledgeGraphVersion, KnowledgePoint,
    PracticeSession, Question, QuestionKnowledgePoint, User, VariantGeneration,
)
from app.services.variant_generation import (
    VariantGenerationError, candidate_fingerprint, create_variant_session,
    generate_candidate, is_variant_supported, validate_candidate,
)


NUMERIC_BLUEPRINT = {
    "version": 1,
    "template": "function_value_numeric",
    "degree": 2,
    "variable": "x",
    "coefficient_range": [-5, 5],
    "input_range": [-3, 3],
    "variation_dimensions": ["coefficients", "input"],
}


def test_numeric_template_is_reproducible_and_program_verified():
    first = generate_candidate(NUMERIC_BLUEPRINT, 20260824, "coefficients")
    second = generate_candidate(NUMERIC_BLUEPRINT, 20260824, "coefficients")
    assert first == second
    assert first.question_type == "numeric_fill"
    assert validate_candidate(first)["equivalence_checked"] is True
    assert candidate_fingerprint(first) == candidate_fingerprint(second)


def test_expression_template_rejects_unknown_dimension_and_verifies_equivalence():
    blueprint = {
        "version": 1, "template": "polynomial_expand_expression", "variable": "x",
        "coefficient_range": [-4, 4], "variation_dimensions": ["factors"],
    }
    candidate = generate_candidate(blueprint, 17, "factors")
    assert candidate.question_type == "expression_fill"
    assert validate_candidate(candidate)["schema_checked"] is True
    with pytest.raises(VariantGenerationError, match="变化维度"):
        generate_candidate(blueprint, 17, "malicious_prompt")


@pytest.mark.asyncio
async def test_variant_session_is_owner_bound_idempotent_and_draft_isolated(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        course = Course(id="course-v", code="calculus", name="高等数学", subject="math")
        version = KnowledgeGraphVersion(id="version-v", course_id="course-v", version="1.0", name="V1", status="published")
        chapter = Chapter(id="chapter-v", course_id="course-v", version_id="version-v", code="c1", name="函数")
        point = KnowledgePoint(id="point-v", course_id="course-v", version_id="version-v", chapter_id="chapter-v", code="function-value", name="函数值")
        users = [
            User(id="variant-owner", username="variant-owner", email="owner@example.test", password_hash="x"),
            User(id="variant-other", username="variant-other", email="other@example.test", password_hash="x"),
        ]
        db.add_all([course, version, chapter, point, *users])
        await db.flush()
        source = Question(
            id="Q-VARIANT-SOURCE", content="已知 f(x)=x^2，求 f(2)", question_type="numeric_fill",
            answer="4", answer_spec={"version": 1, "kind": "numeric_fill", "value": "4"},
            category="高数", course_id="course-v", version_id="version-v", review_status="published",
            is_active=True, grading_mode="deterministic", practice_eligible=True,
            exam_eligible=True, auto_grading_eligible=True, variant_blueprint=NUMERIC_BLUEPRINT,
        )
        db.add(source)
        await db.flush()
        db.add(QuestionKnowledgePoint(question_id=source.id, knowledge_point_id=point.id, is_primary=True))
        error = ErrorItem(
            user_id="variant-owner", item_id="error-v", question=source.content,
            question_type="numeric_fill", question_id=source.id, source="attempt",
            knowledge_point_codes=[point.code],
        )
        db.add(error)
        await db.commit()

    result = await create_variant_session("variant-owner", "error-v", "variant-idempotency-1")
    replay = await create_variant_session("variant-owner", "error-v", "variant-idempotency-1")
    assert replay == result
    async with factory() as db:
        generated = await db.get(Question, result["question_id"])
        generation = await db.get(VariantGeneration, result["generation_id"])
        session = await db.get(PracticeSession, result["session_id"])
        assert generated.review_status == "draft" and generated.is_ai_generated is True
        assert generated.practice_eligible is False and generated.exam_eligible is False
        assert generation.user_id == "variant-owner" and generation.validation_report["equivalence_checked"] is True
        assert session.config_snapshot["review_kind"] == "variant_correct"
        assert session.config_snapshot["error_item_id"] == "error-v"
        assert is_variant_supported(generated) is False

    with pytest.raises(VariantGenerationError) as cross_owner:
        await create_variant_session("variant-other", "error-v", "variant-idempotency-2")
    assert cross_owner.value.code == "ERROR_ITEM_NOT_FOUND"
    with pytest.raises(VariantGenerationError) as conflict:
        await create_variant_session("variant-owner", "error-v", "variant-idempotency-1", "input")
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    await engine.dispose()
