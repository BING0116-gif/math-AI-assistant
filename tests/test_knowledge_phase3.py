import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, KnowledgeGraphVersion, KnowledgePoint, KnowledgePointResource,
    OutboxEvent, Question, QuestionKnowledgePoint, SourceDocument,
)
from app.services.derivative_content import DERIVATIVE_POINTS, GOLDEN
from app.services.knowledge_catalog import get_published_course_tree, get_published_learning_content
from app.services.knowledge_content import (
    ResourcePublishingError, reconcile_published_resources, repair_resource_projection,
    review_and_publish_resource, seed_derivative_phase3, validate_prerequisite_dag,
    validate_resource_math,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase3_seed_is_idempotent_and_publishes_complete_derivative_sample(session_factory):
    async with session_factory() as session:
        course = await seed_derivative_phase3(session)
        await seed_derivative_phase3(session)
        await session.commit()

        version = await session.scalar(select(KnowledgeGraphVersion).where(
            KnowledgeGraphVersion.course_id == course.id,
            KnowledgeGraphVersion.version == "2.0",
        ))
        assert version.status == "published"
        assert course.default_version_id == version.id

        derivative_points = list((await session.scalars(select(KnowledgePoint).where(
            KnowledgePoint.version_id == version.id,
            KnowledgePoint.code.in_([row[0] for row in DERIVATIVE_POINTS]),
        ))).all())
        assert len(derivative_points) == 22
        assert len({point.code for point in derivative_points}) == 22
        validate_prerequisite_dag(list((await session.scalars(
            select(KnowledgePoint).where(KnowledgePoint.version_id == version.id)
        )).all()))

        resources = list((await session.scalars(select(KnowledgePointResource).join(KnowledgePoint).where(
            KnowledgePoint.version_id == version.id,
            KnowledgePoint.code.in_(list(GOLDEN)),
        ))).all())
        assert len(resources) == 50
        assert all(row.status == "published" for row in resources)
        assert all(row.math_validation_status == "passed" for row in resources)
        assert all(row.source_document_id and row.content_hash for row in resources)
        assert not any("将在这里" in row.body for row in resources)
        assert len({row.external_key for row in resources}) == 50

        links = list((await session.scalars(select(QuestionKnowledgePoint).join(KnowledgePoint).where(
            KnowledgePoint.version_id == version.id,
            KnowledgePoint.code.in_(list(GOLDEN)),
        ))).all())
        assert len(links) == 25
        questions = list((await session.scalars(select(Question).where(Question.id.in_([row.question_id for row in links])))).all())
        assert all(row.review_status == "published" and row.practice_eligible for row in questions)

        tree = await get_published_course_tree(session, course.id)
        assert [chapter["name"] for chapter in tree["chapters"]] == ["函数、极限与连续", "导数与微分"]
        point = next(row for row in derivative_points if row.code == "derivative-definition")
        lesson = await get_published_learning_content(session, point.id)
        assert {row["type"] for row in lesson["resources"]} >= {
            "intuition", "definition", "formula", "worked_example", "common_error", "checkpoint", "exercise_set"
        }
        exercise = next(row for row in lesson["resources"] if row["type"] == "exercise_set")
        assert len(exercise["metadata"]["question_ids"]) == 5
        assert lesson["resources"][0]["source"]["document_id"]

        event_count = await session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.aggregate_type == "knowledge_resource"
        ))
        assert event_count == 50
        report = await reconcile_published_resources(session, version.id)
        assert report["published"] == 50
        assert len(report["pending"]) == 50
        assert report["missing"] == []
        assert report["stale"] == []
        assert report["dead"] == []


@pytest.mark.asyncio
async def test_unlicensed_or_placeholder_resource_cannot_publish(session_factory):
    async with session_factory() as session:
        source = SourceDocument(
            original_filename="unknown.md", storage_key="test/unknown", sha256="a" * 64,
            mime_type="text/markdown", size_bytes=1, created_by="tester",
            source_name="unknown", license_type=None, license_evidence_ref=None,
        )
        session.add(source)
        await session.flush()
        resource = KnowledgePointResource(
            knowledge_point_id="missing", source_document_id=source.id,
            resource_type="definition", title="bad", body="TODO 待补充", status="draft",
        )
        with pytest.raises(ResourcePublishingError, match="SOURCE_LICENSE_NOT_VERIFIED"):
            await review_and_publish_resource(session, resource, "reviewer")


@pytest.mark.asyncio
async def test_validation_is_hash_bound_and_review_must_be_independent(session_factory):
    async with session_factory() as session:
        course = await seed_derivative_phase3(session)
        point = await session.scalar(select(KnowledgePoint).where(
            KnowledgePoint.course_id == course.id,
            KnowledgePoint.code == "derivative-definition",
        ))
        source = await session.scalar(select(SourceDocument).where(SourceDocument.license_type == "PROJECT-ORIGINAL"))
        resource = KnowledgePointResource(
            knowledge_point_id=point.id,
            source_document_id=source.id,
            external_key="validation-gate-test",
            source_locator="test#validation",
            resource_type="definition",
            title="独立审核测试",
            body="导数使用极限定义。",
            status="draft",
        )
        session.add(resource)
        await session.flush()

        with pytest.raises(ResourcePublishingError, match="MATH_VALIDATION_REQUIRED"):
            await review_and_publish_resource(session, resource, "reviewer")
        validate_resource_math(resource, "validator")
        with pytest.raises(ResourcePublishingError, match="INDEPENDENT_REVIEW_REQUIRED"):
            await review_and_publish_resource(session, resource, "validator")
        resource.body = "正文变更后原验证失效。"
        with pytest.raises(ResourcePublishingError, match="MATH_VALIDATION_REQUIRED"):
            await review_and_publish_resource(session, resource, "reviewer")


@pytest.mark.asyncio
async def test_reconciliation_detects_stale_and_enqueues_idempotent_repair(session_factory):
    async with session_factory() as session:
        course = await seed_derivative_phase3(session)
        version = await session.scalar(select(KnowledgeGraphVersion).where(
            KnowledgeGraphVersion.course_id == course.id,
            KnowledgeGraphVersion.version == "2.0",
        ))
        event_row = await session.scalar(select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "knowledge_resource"
        ))
        event_row.payload = {"content_hash": "stale"}
        report = await reconcile_published_resources(session, version.id)
        assert event_row.aggregate_id in report["stale"]
        repaired = await repair_resource_projection(session, version.id)
        assert event_row.aggregate_id in repaired["repair_enqueued"]
        await repair_resource_projection(session, version.id)
        repairs = list((await session.scalars(select(OutboxEvent).where(
            OutboxEvent.idempotency_key.like("knowledge-resource-repair:%")
        ))).all())
        assert len(repairs) == 1
