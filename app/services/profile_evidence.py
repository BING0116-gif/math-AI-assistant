"""画像证据链：LearningRecord → Memory → ProfileSnapshot dimension。"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.data.database import get_db_session
from app.data.models import LearningRecord, Memory, MemoryEvidence, ProfileEvidence
from app.services.mastery_evidence import compute_mastery_evidence, unique_evidence


AUDIT_MEMORY_TYPE = "mastery_evidence"
# memories.expire_at 是历史 Integer epoch 字段；用 int32 上限表达长期保留，
# 避免“当前时间 + 100 年”在 PostgreSQL 上溢出。
AUDIT_MEMORY_EXPIRE_AT = 2_147_483_647


def _snapshot_dimensions(snapshot) -> dict[str, dict[str, Any]]:
    dimensions: dict[str, dict[str, Any]] = {}
    for skill in snapshot.skills:
        code = str(skill.get("skill_code") or "").strip()
        if code:
            dimensions[code] = {
                "value": float(skill.get("mastery_level") or 0),
                "evidence_count": int(skill.get("evidence_count") or 0),
                "confidence_level": skill.get("confidence_level") or "insufficient",
            }
    for point in snapshot.weak_points:
        code = str(point.get("category") or "").strip()
        if code and code not in dimensions:
            dimensions[code] = {
                "value": float(point.get("mastery_score", point.get("mastery", 0)) or 0),
                "evidence_count": int(point.get("evidence_count", point.get("count", 0)) or 0),
                "confidence_level": point.get("confidence_level") or "insufficient",
            }
    return dimensions


def _snapshot_id(user_id: str, snapshot, evidence_ids: list[int]) -> str:
    """同一用户、同一事实集和同一画像结论生成稳定快照 ID。"""
    payload = {
        "user_id": user_id,
        "evidence_ids": sorted(evidence_ids),
        "dimensions": _snapshot_dimensions(snapshot),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"ps_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]}"


def _level(score: float) -> str:
    if score >= 0.8:
        return "强"
    if score >= 0.6:
        return "稳步提升"
    if score >= 0.35:
        return "弱"
    return "需重点巩固"


def _event_summary(record: LearningRecord) -> str:
    result = "答对" if record.is_correct else "答错"
    question = " ".join((record.question_content or "").split())[:120]
    detail = f"：{question}" if question else ""
    if record.error_reason:
        detail += f"；{record.error_reason[:80]}"
    return f"{result}{detail}"


class ProfileEvidenceService:
    """在 SQL 中写入、读取 owner-scoped 的画像审计边。"""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_db_session

    async def record_snapshot(self, snapshot) -> str:
        """沉淀可读记忆并记录快照维度边；重放不会产生重复边。"""
        user_id = snapshot.user_id
        async with self._session_factory() as db:
            records = list((await db.execute(
                select(LearningRecord).where(LearningRecord.user_id == user_id)
                .order_by(LearningRecord.created_at, LearningRecord.id)
            )).scalars())
            records = unique_evidence(records)
            snapshot_id = _snapshot_id(user_id, snapshot, [row.id for row in records])
            snapshot.snapshot_id = snapshot_id
            if not records:
                await db.commit()
                return snapshot_id

            grouped: dict[str, list[LearningRecord]] = defaultdict(list)
            for record in records:
                codes = (record.metadata_ or {}).get("knowledge_point_codes") or []
                dimensions = [str(code).strip() for code in codes if str(code).strip()]
                if not dimensions and record.category:
                    dimensions = [record.category]
                for dimension in dict.fromkeys(dimensions):
                    grouped[dimension].append(record)

            dimension_values = _snapshot_dimensions(snapshot)
            now_ts = int(time.time())
            now_dt = datetime.now(timezone.utc)
            for dimension, dimension_records in sorted(grouped.items()):
                computed_score, computed_count, computed_confidence = compute_mastery_evidence(
                    dimension_records
                )
                profile_value = dimension_values.get(dimension, {})
                score = float(profile_value.get("value", computed_score))
                evidence_count = int(profile_value.get("evidence_count", computed_count))
                confidence = profile_value.get("confidence_level", computed_confidence)
                record_ids = sorted(row.id for row in dimension_records)
                source_digest = hashlib.sha256(
                    f"{user_id}:{dimension}:{','.join(map(str, record_ids))}".encode("utf-8")
                ).hexdigest()[:40]
                source_id = f"audit:{source_digest}"

                memory = (await db.execute(select(Memory).where(
                    Memory.user_id == user_id,
                    Memory.memory_type == AUDIT_MEMORY_TYPE,
                    Memory.source_id == source_id,
                    Memory.deleted_at.is_(None),
                ))).scalar_one_or_none()
                if memory is None:
                    content = {
                        "dimension": dimension,
                        "mastery_score": round(score, 4),
                        "evidence_count": evidence_count,
                        "confidence_level": confidence,
                        "conclusion": f"{dimension}掌握度 {score:.2f}（{_level(score)}）",
                    }
                    memory = Memory(
                        user_id=user_id,
                        memory_type=AUDIT_MEMORY_TYPE,
                        high_category="profile_evidence",
                        category=dimension[:64],
                        content=json.dumps(content, ensure_ascii=False, sort_keys=True),
                        embedding_summary=content["conclusion"],
                        importance=0.9,
                        status="active",
                        expire_at=AUDIT_MEMORY_EXPIRE_AT,
                        memory_strength=max(0.1, min(1.0, score)),
                        source_id=source_id,
                        created_at=now_ts,
                        last_accessed=now_ts,
                    )
                    db.add(memory)
                    await db.flush()

                # SQL 是真值；outbox 让 Qdrant 加速层最终一致，也可修复旧的漏投递。
                from app.services.outbox import enqueue_outbox

                await enqueue_outbox(
                    db,
                    event_type="memory.vector.upsert",
                    aggregate_type="memory",
                    aggregate_id=str(memory.id),
                    user_id=user_id,
                    idempotency_key=(
                        f"memory-vector-upsert:{memory.id}:active:"
                        f"{AUDIT_MEMORY_EXPIRE_AT}"
                    ),
                )

                existing_record_ids = set((await db.execute(
                    select(MemoryEvidence.learning_record_id).where(
                        MemoryEvidence.memory_id == memory.id,
                        MemoryEvidence.user_id == user_id,
                    )
                )).scalars())
                for record in dimension_records:
                    if record.id not in existing_record_ids:
                        db.add(MemoryEvidence(
                            memory_id=memory.id,
                            learning_record_id=record.id,
                            user_id=user_id,
                            created_at=now_dt,
                        ))

                edge_exists = (await db.execute(select(ProfileEvidence.id).where(
                    ProfileEvidence.profile_snapshot_id == snapshot_id,
                    ProfileEvidence.dimension == dimension,
                    ProfileEvidence.memory_id == memory.id,
                    ProfileEvidence.user_id == user_id,
                ))).scalar_one_or_none()
                if edge_exists is None:
                    db.add(ProfileEvidence(
                        profile_snapshot_id=snapshot_id,
                        dimension=dimension,
                        memory_id=memory.id,
                        user_id=user_id,
                        created_at=now_dt,
                    ))
            await db.commit()
            return snapshot_id

    async def explain(
        self,
        user_id: str,
        dimension: str,
        *,
        profile_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """读取当前或指定历史快照的一条完整证据链。"""
        async with self._session_factory() as db:
            snapshot_id = profile_snapshot_id
            if snapshot_id is None:
                snapshot_id = (await db.execute(
                    select(ProfileEvidence.profile_snapshot_id)
                    .where(
                        ProfileEvidence.user_id == user_id,
                        ProfileEvidence.dimension == dimension,
                    )
                    .group_by(ProfileEvidence.profile_snapshot_id)
                    .order_by(func.max(ProfileEvidence.created_at).desc())
                    .limit(1)
                )).scalar_one_or_none()
            if snapshot_id is None:
                return {
                    "profile_snapshot_id": None,
                    "dimension": dimension,
                    "conclusion": f"{dimension}暂无足够的独立作答证据",
                    "supporting_memories": [],
                }

            memories = list((await db.execute(
                select(Memory)
                .join(ProfileEvidence, ProfileEvidence.memory_id == Memory.id)
                .where(
                    ProfileEvidence.user_id == user_id,
                    ProfileEvidence.dimension == dimension,
                    ProfileEvidence.profile_snapshot_id == snapshot_id,
                    Memory.user_id == user_id,
                )
                .order_by(Memory.created_at.desc(), Memory.id.desc())
            )).scalars())
            supporting = []
            conclusion = f"{dimension}暂无足够的独立作答证据"
            for memory in memories:
                try:
                    content = json.loads(memory.content)
                except (TypeError, json.JSONDecodeError):
                    content = {}
                conclusion = content.get("conclusion") or conclusion
                events = list((await db.execute(
                    select(LearningRecord)
                    .join(
                        MemoryEvidence,
                        MemoryEvidence.learning_record_id == LearningRecord.id,
                    )
                    .where(
                        MemoryEvidence.memory_id == memory.id,
                        MemoryEvidence.user_id == user_id,
                        LearningRecord.user_id == user_id,
                    )
                    .order_by(LearningRecord.created_at, LearningRecord.id)
                )).scalars())
                supporting.append({
                    "memory_id": memory.id,
                    "content": memory.embedding_summary or memory.content,
                    "evidence_events": [
                        {
                            "learning_record_id": event.id,
                            "event_type": event.event_type,
                            "at": event.created_at,
                            "summary": _event_summary(event),
                            "is_correct": event.is_correct,
                        }
                        for event in events
                    ],
                })
            return {
                "profile_snapshot_id": snapshot_id,
                "dimension": dimension,
                "conclusion": conclusion,
                "supporting_memories": supporting,
            }
