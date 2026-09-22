"""Governed publishing, reconciliation and Phase 3 derivative content seed."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.data.models import (
    Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, KnowledgePointResource,
    OutboxEvent, Question, QuestionKnowledgePoint, SourceDocument,
)
from app.services.derivative_content import DERIVATIVE_POINTS, GOLDEN, resources_for
from app.services.calculus_phase5 import CHAPTERS as PHASE5_CHAPTERS, POINTS as PHASE5_POINTS
from app.services.phase5_content import GOLDEN as PHASE5_GOLDEN, GOLDEN_IMPORTANCE, phase5_resources_for
from app.services.phase5_practice import PRACTICE as PHASE5_PRACTICE
from app.services.knowledge_seed import seed_phase_one_calculus
from app.services.outbox import enqueue_outbox

VERSION = "2.0"
PHASE5_VERSION = "3.0"
PLACEHOLDER_MARKERS = ("将在这里", "TODO", "待补充", "占位")
ALLOWED_LICENSES = {"PROJECT-ORIGINAL", "CC-BY-4.0", "CC-BY-NC-SA-4.0"}
REQUIRED_GOLDEN_RESOURCE_TYPES = {
    "intuition", "definition", "formula", "worked_example", "common_error",
    "checkpoint", "exercise_set", "summary",
}


class ResourcePublishingError(ValueError):
    pass


def validate_math_body(body: str) -> list[str]:
    errors: list[str] = []
    if any(marker.lower() in body.lower() for marker in PLACEHOLDER_MARKERS):
        errors.append("PLACEHOLDER_CONTENT")
    if body.count("$") % 2:
        errors.append("UNBALANCED_MATH_DELIMITER")
    for left, right in (("{", "}"), ("(", ")"), ("[", "]")):
        if body.count(left) != body.count(right):
            errors.append(f"UNBALANCED_{left}{right}")
    return errors


def validate_prerequisite_dag(points: list[KnowledgePoint]) -> None:
    graph = {p.code: [code for code in (p.prerequisites or []) if code in {x.code for x in points}] for p in points}
    state: dict[str, int] = {}

    def visit(code: str) -> None:
        if state.get(code) == 1:
            raise ResourcePublishingError(f"PREREQUISITE_CYCLE:{code}")
        if state.get(code) == 2:
            return
        state[code] = 1
        for dependency in graph.get(code, []):
            visit(dependency)
        state[code] = 2

    for code in graph:
        visit(code)


def validate_resource_math(
    resource: KnowledgePointResource,
    validator_id: str,
    *,
    method: str = "deterministic-structure-and-editorial-attestation-v1",
) -> None:
    """Record hash-bound validation evidence without conflating it with review.

    This verifier deliberately fails closed: changing the body invalidates the
    attestation, and the later reviewer must be a different actor.
    """
    if not validator_id.strip():
        raise ResourcePublishingError("MATH_VALIDATOR_REQUIRED")
    errors = validate_math_body(resource.body)
    if errors:
        resource.math_validation_status = "failed"
        raise ResourcePublishingError(",".join(errors))
    content_hash = hashlib.sha256(resource.body.encode("utf-8")).hexdigest()
    metadata = dict(resource.metadata_ or {})
    metadata["math_validation"] = {
        "validator_id": validator_id,
        "method": method,
        "content_hash": content_hash,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    resource.metadata_ = metadata
    resource.content_hash = content_hash
    resource.math_validation_status = "passed"


async def review_and_publish_resource(session, resource: KnowledgePointResource, reviewer_id: str) -> None:
    source = await session.get(SourceDocument, resource.source_document_id) if resource.source_document_id else None
    if source is None or source.license_type not in ALLOWED_LICENSES or not source.license_evidence_ref:
        raise ResourcePublishingError("SOURCE_LICENSE_NOT_VERIFIED")
    if not reviewer_id.strip():
        raise ResourcePublishingError("REVIEWER_REQUIRED")
    content_hash = hashlib.sha256(resource.body.encode("utf-8")).hexdigest()
    validation = (resource.metadata_ or {}).get("math_validation") or {}
    if (
        resource.math_validation_status != "passed"
        or validation.get("content_hash") != content_hash
        or not validation.get("validator_id")
        or not validation.get("method")
    ):
        raise ResourcePublishingError("MATH_VALIDATION_REQUIRED")
    if validation["validator_id"] == reviewer_id:
        raise ResourcePublishingError("INDEPENDENT_REVIEW_REQUIRED")
    now = datetime.now(timezone.utc)
    resource.content_hash = content_hash
    resource.status = "reviewed"
    resource.reviewed_by = reviewer_id
    resource.reviewed_at = now
    resource.status = "published"
    resource.published_at = now
    await session.flush()
    await enqueue_outbox(
        session,
        event_type="knowledge_resource.vector.upsert",
        aggregate_type="knowledge_resource",
        aggregate_id=resource.id,
        idempotency_key=f"knowledge-resource:{resource.id}:{resource.content_hash}",
        payload={"content_hash": resource.content_hash},
    )


async def _source(session) -> SourceDocument:
    sha = hashlib.sha256(b"math-ai-derivative-phase3-original-v1").hexdigest()
    row = await session.scalar(select(SourceDocument).where(SourceDocument.sha256 == sha))
    if row is None:
        row = SourceDocument(
            original_filename="derivative-phase3-editorial.md",
            storage_key="editorial/derivative-phase3-v1",
            sha256=sha,
            mime_type="text/markdown",
            created_by="system",
            source_name="Math AI Assistant 原创内容；范围参考 OpenStax Calculus Volume 1 Chapter 3",
            license_type="PROJECT-ORIGINAL",
            license_note="中文正文为项目原创；OpenStax 仅作概念范围参考，不复制原文。参考材料为 CC BY-NC-SA 4.0。",
            license_evidence_ref="https://openstax.org/books/calculus-volume-1/pages/preface",
            license_confirmed_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.flush()
    return row


async def _phase5_source(session) -> SourceDocument:
    sha = hashlib.sha256(b"math-ai-phase5-original-v1").hexdigest()
    row = await session.scalar(select(SourceDocument).where(SourceDocument.sha256 == sha))
    if row is None:
        row = SourceDocument(
            original_filename="phase5-editorial.md",
            storage_key="editorial/phase5-v1",
            sha256=sha,
            mime_type="text/markdown",
            created_by="system",
            source_name="Math AI Assistant 原创内容；范围参考 OpenStax Calculus Volume 1 Chapters 4-6",
            license_type="PROJECT-ORIGINAL",
            license_note="中文正文为项目原创；OpenStax 仅作概念范围参考，不复制原文。参考材料为 CC BY-NC-SA 4.0。",
            license_evidence_ref="https://openstax.org/books/calculus-volume-1/pages/preface",
            license_confirmed_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.flush()
    return row


async def _clone_phase_one_taxonomy(session, course: Course, source_version, target_version) -> dict[str, KnowledgePoint]:
    source_chapters = list((await session.scalars(select(Chapter).where(Chapter.version_id == source_version.id).order_by(Chapter.level, Chapter.sort_order))).all())
    chapter_map: dict[str, Chapter] = {}
    for old in source_chapters:
        row = await session.scalar(select(Chapter).where(Chapter.version_id == target_version.id, Chapter.code == old.code))
        if row is None:
            row = Chapter(course_id=course.id, version_id=target_version.id, code=old.code, name=old.name, description=old.description, sort_order=old.sort_order, level=old.level)
            session.add(row)
            await session.flush()
        chapter_map[old.id] = row
    for old in source_chapters:
        chapter_map[old.id].parent_id = chapter_map[old.parent_id].id if old.parent_id else None

    point_map: dict[str, KnowledgePoint] = {}
    source_points = list((await session.scalars(select(KnowledgePoint).where(KnowledgePoint.version_id == source_version.id))).all())
    for old in source_points:
        row = await session.scalar(select(KnowledgePoint).where(KnowledgePoint.version_id == target_version.id, KnowledgePoint.code == old.code))
        if row is None:
            row = KnowledgePoint(
                course_id=course.id, version_id=target_version.id, chapter_id=chapter_map[old.chapter_id].id,
                code=old.code, name=old.name, description=old.description, aliases=old.aliases,
                learning_objectives=old.learning_objectives, common_errors=old.common_errors,
                key_concepts=old.key_concepts, key_formulas=old.key_formulas, exam_focuses=old.exam_focuses,
                prerequisites=old.prerequisites, related=old.related, difficulty=old.difficulty,
                importance=old.importance, sort_order=old.sort_order, status=old.status,
            )
            session.add(row)
            await session.flush()
        point_map[row.code] = row
    return point_map


async def _clone_published_resources(session, source_version, points: dict[str, KnowledgePoint]) -> None:
    """Copy visible lesson assets into a new version without reusing unique keys."""
    resources = list((await session.scalars(
        select(KnowledgePointResource)
        .join(KnowledgePoint)
        .where(KnowledgePoint.version_id == source_version.id, KnowledgePointResource.status == "published")
    )).all())
    source_points = {row.id: row.code for row in (await session.scalars(
        select(KnowledgePoint).where(KnowledgePoint.version_id == source_version.id)
    )).all()}
    for old in resources:
        code = source_points.get(old.knowledge_point_id)
        if not code or code not in points:
            continue
        external_key = f"phase5:{code}:{old.resource_type}:{old.sort_order}"
        row = await session.scalar(select(KnowledgePointResource).where(
            KnowledgePointResource.external_key == external_key
        ))
        if row is None:
            row = KnowledgePointResource(
                knowledge_point_id=points[code].id,
                external_key=external_key,
                resource_type=old.resource_type,
                title=old.title,
            )
            session.add(row)
        row.body = old.body
        row.metadata_ = old.metadata_
        row.sort_order = old.sort_order
        row.status = "published"
        row.math_validation_status = old.math_validation_status
        row.source_document_id = old.source_document_id
        row.source_locator = old.source_locator
        row.content_hash = old.content_hash
        row.reviewed_by = old.reviewed_by
        row.reviewed_at = old.reviewed_at
        row.published_at = old.published_at


async def chapter_completeness_report(session, chapter_id: str) -> dict:
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None:
        raise ResourcePublishingError("CHAPTER_NOT_FOUND")
    child_ids = list((await session.scalars(select(Chapter.id).where(Chapter.parent_id == chapter.id))).all())
    chapter_ids = [chapter.id, *child_ids]
    points = list((await session.scalars(select(KnowledgePoint).where(
        KnowledgePoint.chapter_id.in_(chapter_ids), KnowledgePoint.status == "active"
    ))).all())
    issues: list[dict] = []
    codes = {point.code for point in (await session.scalars(select(KnowledgePoint).where(
        KnowledgePoint.version_id == chapter.version_id
    ))).all()}
    point_ids = [point.id for point in points]
    published_resources = list((await session.scalars(
        select(KnowledgePointResource).where(
            KnowledgePointResource.knowledge_point_id.in_(point_ids),
            KnowledgePointResource.status == "published",
        )
    )).all()) if point_ids else []
    resources_by_point: dict[str, set[str]] = {}
    for resource in published_resources:
        resources_by_point.setdefault(resource.knowledge_point_id, set()).add(resource.resource_type)
    for point in points:
        missing = []
        if not point.description.strip():
            missing.append("description")
        if not point.learning_objectives:
            missing.append("learning_objectives")
        unknown = sorted(set(point.prerequisites or []) - codes)
        text = " ".join([point.name, point.description, *(point.learning_objectives or [])])
        if any(marker.lower() in text.lower() for marker in PLACEHOLDER_MARKERS):
            missing.append("placeholder_content")
        if unknown:
            missing.append(f"unknown_prerequisites:{','.join(unknown)}")
        if point.importance >= 0.9:
            missing_types = sorted(REQUIRED_GOLDEN_RESOURCE_TYPES - resources_by_point.get(point.id, set()))
            if missing_types:
                missing.append(f"missing_resources:{','.join(missing_types)}")
        if missing:
            issues.append({"point_code": point.code, "issues": missing})
    return {
        "chapter_id": chapter.id,
        "point_count": len(points),
        "complete": bool(points) and not issues,
        "issues": issues or ([] if points else [{"point_code": None, "issues": ["empty_chapter"]}]),
    }


async def publish_chapter(session, chapter_id: str, reviewer_id: str) -> dict:
    chapter = await session.get(Chapter, chapter_id)
    report = await chapter_completeness_report(session, chapter_id)
    if not report["complete"]:
        raise ResourcePublishingError("CHAPTER_INCOMPLETE")
    now = datetime.now(timezone.utc)
    chapter.status = "published"
    chapter.published_by = reviewer_id
    chapter.published_at = now
    children = list((await session.scalars(select(Chapter).where(Chapter.parent_id == chapter.id))).all())
    for child in children:
        child.status = "published"
        child.published_by = reviewer_id
        child.published_at = now
    return report


async def withdraw_chapter(session, chapter_id: str) -> None:
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None:
        raise ResourcePublishingError("CHAPTER_NOT_FOUND")
    chapter.status = "withdrawn"
    for child in (await session.scalars(select(Chapter).where(Chapter.parent_id == chapter.id))).all():
        child.status = "withdrawn"


async def seed_calculus_phase5(session, reviewer_id: str = "phase5-editor") -> Course:
    """Create an idempotent 98-point draft without bypassing Phase 5 gates."""
    course = await seed_derivative_phase3(session, reviewer_id)
    await session.flush()
    source_version = await session.scalar(select(KnowledgeGraphVersion).where(
        KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == VERSION
    ))
    version = await session.scalar(select(KnowledgeGraphVersion).where(
        KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == PHASE5_VERSION
    ))
    if version is None:
        version = KnowledgeGraphVersion(
            course_id=course.id, version=PHASE5_VERSION, name="高等数学上册完整路径",
            status="draft", based_on_version_id=source_version.id, created_by=reviewer_id,
        )
        session.add(version)
        await session.flush()
    points = await _clone_phase_one_taxonomy(session, course, source_version, version)
    await _clone_published_resources(session, source_version, points)

    chapters: dict[str, Chapter] = {}
    for code, name, description, order in PHASE5_CHAPTERS:
        root = await session.scalar(select(Chapter).where(Chapter.version_id == version.id, Chapter.code == code))
        if root is None:
            root = Chapter(
                course_id=course.id, version_id=version.id, code=code, name=name,
                description=description, sort_order=order, level=1, status="draft",
            )
            session.add(root)
            await session.flush()
        chapters[code] = root

    for code, name, chapter_code, order, difficulty, prerequisites in PHASE5_POINTS:
        point = await session.scalar(select(KnowledgePoint).where(
            KnowledgePoint.version_id == version.id, KnowledgePoint.code == code
        ))
        if point is None:
            point = KnowledgePoint(
                course_id=course.id, version_id=version.id, chapter_id=chapters[chapter_code].id,
                code=code, name=name, sort_order=order,
            )
            session.add(point)
        point.chapter_id = chapters[chapter_code].id
        point.description = PHASE5_GOLDEN[code]["description"] if code in PHASE5_GOLDEN else f"理解{name}的核心条件，掌握规范计算方法，并能用于典型高等数学问题。"
        point.aliases = []
        point.learning_objectives = [f"说明{name}的适用条件", f"完成{name}的典型计算或证明"]
        point.common_errors = ["忽略适用条件", "计算后未检查定义域或收敛性"]
        point.key_concepts = [name]
        point.exam_focuses = ["条件辨析", "规范计算", "综合应用"]
        point.prerequisites = prerequisites
        point.related = []
        point.difficulty = difficulty
        point.importance = GOLDEN_IMPORTANCE if code in PHASE5_GOLDEN else 0.78
        point.status = "active"
        points[code] = point
    await session.flush()
    validate_prerequisite_dag(list(points.values()))

    # Phase 5 golden lessons: full resources plus graded practice items,
    # released through the same validate -> independent review pipeline.
    golden_source = await _phase5_source(session)
    chapter_names = {code: name for code, name, _, _ in PHASE5_CHAPTERS}
    point_chapter = {code: chapter_code for code, _, chapter_code, _, _, _ in PHASE5_POINTS}
    for index, (code, items) in enumerate(PHASE5_PRACTICE.items(), start=1):
        point = points[code]
        for resource_order, (kind, title, body) in enumerate(phase5_resources_for(code), start=1):
            external_key = f"phase5-golden:{code}:{kind}:{resource_order}"
            resource = await session.scalar(select(KnowledgePointResource).where(KnowledgePointResource.external_key == external_key))
            if resource is None:
                resource = KnowledgePointResource(knowledge_point_id=point.id, external_key=external_key, resource_type=kind, title=title)
                session.add(resource)
            resource.body = body
            resource.sort_order = resource_order
            resource.source_document_id = golden_source.id
            resource.source_locator = f"phase5-golden-v1#{code}/{kind}/{resource_order}"
            resource.metadata_ = {
                **(resource.metadata_ or {}),
                "schema_version": 1,
                "knowledge_point_code": code,
                "fallback": "text",
                "authoring": "human",
            }
            new_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if resource.status != "published" or resource.content_hash != new_hash:
                resource.status = "draft"
                resource.math_validation_status = "pending"
                validate_resource_math(resource, "phase5-math-verifier")
                await review_and_publish_resource(session, resource, reviewer_id)

        question_ids: list[str] = []
        for sequence, (level, question_difficulty, prompt, options, answer, analysis) in enumerate(items, start=1):
            qid = f"P5{index:02d}{sequence}"
            question_ids.append(qid)
            question = await session.get(Question, qid)
            if question is None:
                question = Question(id=qid, content=f"【{level}】{prompt}", question_type="choice", answer=answer, category=chapter_names[point_chapter[code]])
                session.add(question)
            question.options = [{"id": option_id, "text": text} for option_id, text in options]
            question.answer = answer
            question.answer_spec = {"version": 1, "kind": "choice", "correct": answer}
            question.analysis = analysis
            question.course_id = course.id; question.version_id = version.id
            question.difficulty = question_difficulty; question.source = "phase5-original"
            question.review_status = "published"; question.is_ai_generated = False
            question.grading_mode = "deterministic"
            question.practice_eligible = True; question.exam_eligible = False; question.auto_grading_eligible = True
            link = await session.get(QuestionKnowledgePoint, {"question_id": qid, "knowledge_point_id": point.id})
            if link is None:
                session.add(QuestionKnowledgePoint(question_id=qid, knowledge_point_id=point.id, is_primary=True))
        exercise = await session.scalar(select(KnowledgePointResource).where(
            KnowledgePointResource.knowledge_point_id == point.id,
            KnowledgePointResource.resource_type == "exercise_set",
            KnowledgePointResource.status == "published",
        ))
        if exercise is not None:
            exercise.metadata_ = {**(exercise.metadata_ or {}), "question_ids": question_ids, "levels": ["基础", "常规", "进阶"]}

    # Phase 5 stays an internal draft until every chapter passes the content
    # completeness gate via publish_calculus_phase5. Once released, re-seeding
    # refreshes content in place but must never demote the published version
    # (seed_derivative_phase3 above resets the course default to 2.0).
    if version.status != "published":
        for chapter in (await session.scalars(select(Chapter).where(Chapter.version_id == version.id))).all():
            chapter.status = "draft"
            chapter.published_by = None
            chapter.published_at = None
        version.status = "draft"
        version.published_by = None
        version.published_at = None
    else:
        course.default_version_id = version.id
    return course


async def publish_calculus_phase5(session, reviewer_id: str = "phase5-reviewer") -> dict:
    """Release version 3.0 only after every chapter passes the completeness gate."""
    course = await seed_calculus_phase5(session, reviewer_id)
    await session.flush()
    version = await session.scalar(select(KnowledgeGraphVersion).where(
        KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == PHASE5_VERSION
    ))
    root_chapters = list((await session.scalars(select(Chapter).where(
        Chapter.version_id == version.id, Chapter.level == 1,
    ).order_by(Chapter.sort_order, Chapter.code))).all())
    chapter_reports = []
    for chapter in root_chapters:
        report = await publish_chapter(session, chapter.id, reviewer_id)
        chapter_reports.append({
            "chapter_code": chapter.code,
            "chapter_name": chapter.name,
            "complete": report["complete"],
            "point_count": report["point_count"],
        })
    now = datetime.now(timezone.utc)
    version.status = "published"
    version.published_by = reviewer_id
    version.published_at = now
    course.default_version_id = version.id
    course.description = "高等数学：函数、极限、连续、导数与微分、积分及其应用。"
    active_points = await session.scalar(select(func.count()).select_from(KnowledgePoint).where(
        KnowledgePoint.version_id == version.id, KnowledgePoint.status == "active"
    ))
    return {
        "course_id": course.id,
        "version": PHASE5_VERSION,
        "default_version_id": version.id,
        "point_count": active_points,
        "chapters": chapter_reports,
    }


async def seed_derivative_phase3(session, reviewer_id: str = "phase3-editor") -> Course:
    course = await seed_phase_one_calculus(session)
    await session.flush()
    source_version = await session.scalar(select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.id == course.default_version_id))
    version = await session.scalar(select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == VERSION))
    if version is None:
        version = KnowledgeGraphVersion(course_id=course.id, version=VERSION, name="函数、极限、连续、导数与微分", status="draft", based_on_version_id=source_version.id, created_by=reviewer_id)
        session.add(version)
        await session.flush()
    points = await _clone_phase_one_taxonomy(session, course, source_version, version)

    root = await session.scalar(select(Chapter).where(Chapter.version_id == version.id, Chapter.code == "derivatives-and-differentials"))
    if root is None:
        root = Chapter(course_id=course.id, version_id=version.id, code="derivatives-and-differentials", name="导数与微分", description="从导数定义到微分运算的完整学习路径。", sort_order=2, level=1)
        session.add(root); await session.flush()
    section = await session.scalar(select(Chapter).where(Chapter.version_id == version.id, Chapter.code == "derivative-core"))
    if section is None:
        section = Chapter(course_id=course.id, version_id=version.id, parent_id=root.id, code="derivative-core", name="导数与微分基础", description="导数定义、运算法则、隐式求导、高阶导数与微分。", sort_order=1, level=2)
        session.add(section); await session.flush()

    for code, name, order, difficulty, prerequisites in DERIVATIVE_POINTS:
        row = await session.scalar(select(KnowledgePoint).where(KnowledgePoint.version_id == version.id, KnowledgePoint.code == code))
        if row is None:
            row = KnowledgePoint(course_id=course.id, version_id=version.id, chapter_id=section.id, code=code, name=name, sort_order=order)
            session.add(row)
        row.description = f"掌握{name}的概念、条件与典型应用。"
        row.difficulty = difficulty
        row.importance = 0.9 if code in GOLDEN else 0.75
        row.prerequisites = prerequisites
        row.related = []
        row.learning_objectives = [f"准确说明{name}的核心含义", f"在适用条件下完成{name}相关计算"]
        row.status = "active"
        points[code] = row
    await session.flush()
    validate_prerequisite_dag(list(points.values()))

    source = await _source(session)
    for code in GOLDEN:
        point = points[code]
        for order, (kind, title, body) in enumerate(resources_for(code), start=1):
            external_key = f"phase3:{code}:{kind}:{order}"
            resource = await session.scalar(select(KnowledgePointResource).where(KnowledgePointResource.external_key == external_key))
            if resource is None:
                resource = KnowledgePointResource(knowledge_point_id=point.id, external_key=external_key, resource_type=kind, title=title)
                session.add(resource)
            resource.body = body
            resource.sort_order = order
            resource.source_document_id = source.id
            resource.source_locator = f"derivative-phase3-v1#{code}/{kind}/{order}"
            resource.metadata_ = {
                **(resource.metadata_ or {}),
                "schema_version": 1,
                "knowledge_point_code": code,
                "fallback": "text",
                "authoring": "human",
            }
            new_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if resource.status != "published" or resource.content_hash != new_hash:
                resource.status = "draft"
                resource.math_validation_status = "pending"
                validate_resource_math(resource, "phase3-math-verifier")
                await review_and_publish_resource(session, resource, reviewer_id)

    for index, code in enumerate(GOLDEN, start=1):
        point = points[code]
        question_ids: list[str] = []
        practice_specs = (
            ("基础", 2, "下列关于该知识点的表述，哪一项符合定义与适用条件？"),
            ("基础", 2, "解题时第一步最合理的是哪一项？"),
            ("常规", 3, "下列做法中，哪一项能避免常见概念错误？"),
            ("常规", 3, "完成计算后，最需要补做哪一项检查？"),
            ("进阶", 4, "面对多步综合题，哪一种论证顺序最完整？"),
        )
        for sequence, (level, difficulty, prompt) in enumerate(practice_specs, start=1):
            qid = f"D3{index:02d}{sequence}"
            question_ids.append(qid)
            question = await session.get(Question, qid)
            if question is None:
                question = Question(id=qid, content=f"【{level}】关于“{point.name}”：{prompt}", question_type="choice", answer="A", category="导数与微分")
                session.add(question)
            question.options = [
                {"id": "A", "text": "先核对条件，写明所用定义或法则，再计算并检查结果的定义域。"},
                {"id": "B", "text": "只要形式相似即可套公式，不必检查前提。"},
                {"id": "C", "text": "把趋近过程直接替换为增量等于零。"},
                {"id": "D", "text": "只根据图像外观判断，不需要代数或极限依据。"},
            ]
            question.answer = "A"
            question.answer_spec = {"version": 1, "kind": "choice", "correct": "A"}
            question.analysis = f"{point.name}的规范解题过程必须保留适用条件、依据与结果检查；其余选项都省略了关键数学约束。"
            question.course_id = course.id; question.version_id = version.id
            question.difficulty = difficulty; question.source = "phase3-original"
            question.review_status = "published"; question.is_ai_generated = False
            question.grading_mode = "deterministic"
            question.practice_eligible = True; question.exam_eligible = False; question.auto_grading_eligible = True
            link = await session.get(QuestionKnowledgePoint, {"question_id": qid, "knowledge_point_id": point.id})
            if link is None:
                session.add(QuestionKnowledgePoint(question_id=qid, knowledge_point_id=point.id, is_primary=True))
        exercise = await session.scalar(select(KnowledgePointResource).where(
            KnowledgePointResource.knowledge_point_id == point.id,
            KnowledgePointResource.resource_type == "exercise_set",
            KnowledgePointResource.status == "published",
        ))
        if exercise is not None:
            exercise.metadata_ = {**(exercise.metadata_ or {}), "question_ids": question_ids, "levels": ["基础", "常规", "进阶"]}

    version.status = "published"
    version.published_by = reviewer_id
    version.published_at = datetime.now(timezone.utc)
    course.default_version_id = version.id
    course.description = "高等数学：函数、极限、连续、导数与微分。"
    return course


async def reconcile_published_resources(session, version_id: str) -> dict:
    resources = list((await session.scalars(
        select(KnowledgePointResource).join(KnowledgePoint).where(
            KnowledgePoint.version_id == version_id, KnowledgePointResource.status == "published"
        )
    )).all())
    resource_ids = {row.id for row in resources}
    events = list((await session.scalars(select(OutboxEvent).where(
        OutboxEvent.aggregate_type == "knowledge_resource", OutboxEvent.aggregate_id.in_(resource_ids)
    ))).all()) if resource_ids else []
    latest = {}
    for event in sorted(events, key=lambda row: (row.created_at, row.id)):
        latest[event.aggregate_id] = event
    missing = sorted(resource_ids - set(latest))
    stale = sorted(
        row.id for row in resources
        if row.id in latest and (latest[row.id].payload or {}).get("content_hash") != row.content_hash
    )
    dead = sorted(row.id for row in resources if row.id in latest and latest[row.id].status == "dead")
    pending = sorted(
        row.id for row in resources
        if row.id in latest and latest[row.id].status != "completed" and row.id not in dead
    )
    unsynced = set(missing) | set(stale) | set(dead) | set(pending)
    return {
        "published": len(resources),
        "synced": len(resources) - len(unsynced),
        "missing": missing,
        "stale": stale,
        "dead": dead,
        "pending": pending,
    }


async def repair_resource_projection(session, version_id: str) -> dict:
    """Idempotently enqueue repair events for missing, stale, or dead projections."""
    report = await reconcile_published_resources(session, version_id)
    repair_ids = sorted(set(report["missing"]) | set(report["stale"]) | set(report["dead"]))
    resources = {
        row.id: row for row in (await session.scalars(
            select(KnowledgePointResource).where(KnowledgePointResource.id.in_(repair_ids))
        )).all()
    } if repair_ids else {}
    for resource_id in repair_ids:
        resource = resources.get(resource_id)
        if resource is None:
            continue
        await enqueue_outbox(
            session,
            event_type="knowledge_resource.vector.upsert",
            aggregate_type="knowledge_resource",
            aggregate_id=resource.id,
            idempotency_key=f"knowledge-resource-repair:{resource.id}:{resource.content_hash}",
            payload={"content_hash": resource.content_hash, "repair": True},
        )
    return {**report, "repair_enqueued": repair_ids}
