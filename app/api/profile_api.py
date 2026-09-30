from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field

from app.data.database import get_db_session
from app.data.repositories import UserRepository
from app.api.student_contracts import STUDENT_API_RESPONSES
from app.services.profile_read_models import profile_response, report_response
from app.security.audit import get_audit_logger
from app.security.access_control import verify_resource_ownership

router = APIRouter(prefix="/api/profile", tags=["用户画像"])


class PreferencesUpdateRequest(BaseModel):
    difficulty_mode: Optional[str] = Field(None, description="难度模式: adaptive | fixed")
    preferred_categories: Optional[list[str]] = None
    daily_goal_minutes: Optional[int] = Field(None, ge=5, le=240)


class ProfileEvidenceEventResponse(BaseModel):
    learning_record_id: int
    event_type: str
    at: datetime
    summary: str
    is_correct: bool


class SupportingMemoryResponse(BaseModel):
    memory_id: int
    content: str
    evidence_events: list[ProfileEvidenceEventResponse]


class ProfileWhyResponse(BaseModel):
    profile_snapshot_id: Optional[str]
    dimension: str
    conclusion: str
    supporting_memories: list[SupportingMemoryResponse]


class ProfileWhyEnvelope(BaseModel):
    code: int = 0
    data: ProfileWhyResponse
    message: str = "ok"


class ProfileSummaryResponse(BaseModel):
    total_questions: int
    correct_rate: float
    avg_time_per_question: float
    learning_level: str


class ProfileCapabilityResponse(BaseModel):
    knowledge_mastery: dict[str, float]
    recommended_difficulty: str | int | float


class ProfileResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str
    generated_at: datetime
    summary: ProfileSummaryResponse
    capability: ProfileCapabilityResponse
    behavior: dict[str, Any]
    error_patterns: Any
    progress_trends: Any
    preferences: dict[str, Any]
    recommendations: list[Any] | None = None


class ProfileReportOverview(BaseModel):
    total_questions: int
    correct_rate: float
    avg_time_per_question: float
    recommended_difficulty: str | int | float


class ProfileReportResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str
    generated_at: datetime
    overview: ProfileReportOverview
    weak_points: list[Any]
    strong_points: list[Any]
    error_patterns: Any
    progress_trends: Any
    recommendations: list[Any]


class ProfileRecommendationsResponse(BaseModel):
    user_id: str
    recommendations: list[Any]


class PreferencesUpdateResponse(BaseModel):
    success: bool
    message: str
    preferences: dict[str, Any]


class SkillProfileResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str
    generated_at: datetime
    skill_summary: dict[str, int]
    skills: list[dict[str, Any]]
    error_patterns: Any
    cognitive_style: Any
    next_recommended_skills: list[dict[str, Any]]
    difficulty_estimate_by_category: dict[str, Any]
    compact_profile: str


class TrackLearningRequest(BaseModel):
    content: str = ""
    question_content: str = ""
    source: str = Field(default="api", max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrackLearningResponse(BaseModel):
    success: bool
    tracked_event: dict[str, Any]
    persisted: bool


def _current_user(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return user_id


async def _get_facade():
    from agent_core.memory_persistence import MemoryPersistenceFacade
    return MemoryPersistenceFacade()


# ========================================================================
# /me 系列：一律从认证上下文取 user_id，不接受 path user_id
# ========================================================================


@router.get("/me", response_model=ProfileResponse, responses=STUDENT_API_RESPONSES)
async def get_my_profile(
    http_request: Request,
    include_recommendations: bool = Query(False),
    include_history: bool = Query(False),
):
    user_id = _current_user(http_request)
    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    response = profile_response(
        snapshot, include_recommendations=include_recommendations
    )

    audit_logger = get_audit_logger()
    audit_logger.log_access(
        user_id=user_id,
        resource_type="profile",
        resource_id=user_id,
        action="view_profile",
        ip_address=http_request.client.host if http_request.client else "",
    )
    return response


@router.get("/me/report", response_model=ProfileReportResponse, responses=STUDENT_API_RESPONSES)
async def get_my_report(http_request: Request):
    user_id = _current_user(http_request)
    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    report = report_response(snapshot)

    audit_logger = get_audit_logger()
    audit_logger.log_access(
        user_id=user_id,
        resource_type="report",
        resource_id=user_id,
        action="view_report",
        ip_address=http_request.client.host if http_request.client else "",
    )
    return report


@router.get("/me/recommendations", response_model=ProfileRecommendationsResponse, responses=STUDENT_API_RESPONSES)
async def get_my_recommendations(http_request: Request):
    user_id = _current_user(http_request)
    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)
    return {
        "user_id": user_id,
        "recommendations": snapshot.recommendations,
    }


@router.get("/me/skills", response_model=SkillProfileResponse, responses=STUDENT_API_RESPONSES)
async def get_my_skill_profile(http_request: Request):
    user_id = _current_user(http_request)
    return await _build_skill_profile_response(user_id)


@router.get("/why", response_model=ProfileWhyEnvelope, responses=STUDENT_API_RESPONSES)
async def get_profile_reason(
    http_request: Request,
    dimension: str = Query(..., min_length=1, max_length=100),
    user_id: Optional[str] = Query(None, min_length=1, max_length=36),
    profile_snapshot_id: Optional[str] = Query(None, min_length=1, max_length=64),
):
    """解释画像结论；仅本人或管理员可读取，支持指定历史快照。"""
    target_user_id = user_id or _current_user(http_request)
    verify_resource_ownership(http_request, target_user_id)

    from app.services.profile_evidence import ProfileEvidenceService

    service = ProfileEvidenceService()
    if profile_snapshot_id is None:
        facade = await _get_facade()
        snapshot = await facade.get_profile_snapshot(target_user_id)
        # 迁移前生成的旧快照没有审计标识；首次查询时从 SQL 事实修复。
        if not snapshot.snapshot_id:
            await facade.refresh_profile_snapshot(target_user_id)

    evidence = await service.explain(
        target_user_id,
        dimension,
        profile_snapshot_id=profile_snapshot_id,
    )
    return {"code": 0, "data": evidence, "message": "ok"}


@router.put("/me/preferences", response_model=PreferencesUpdateResponse, responses=STUDENT_API_RESPONSES)
async def update_my_preferences(
    preferences: PreferencesUpdateRequest,
    http_request: Request,
):
    user_id = _current_user(http_request)
    return await _apply_preferences(user_id, preferences, http_request)


# ========================================================================
# 旧路由：保留兼容，校验 ownership 后转发到统一快照实现
# ========================================================================


@router.get("/{user_id}", response_model=ProfileResponse, responses=STUDENT_API_RESPONSES, deprecated=True)
async def get_user_profile(
    user_id: str,
    http_request: Request,
    include_recommendations: bool = Query(False),
    include_history: bool = Query(False),
):
    verify_resource_ownership(http_request, user_id)

    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    response = profile_response(
        snapshot, include_recommendations=include_recommendations
    )

    audit_logger = get_audit_logger()
    audit_logger.log_access(
        user_id=user_id,
        resource_type="profile",
        resource_id=user_id,
        action="view_profile",
        ip_address=http_request.client.host if http_request.client else "",
    )
    return response


@router.get("/{user_id}/report", response_model=ProfileReportResponse, responses=STUDENT_API_RESPONSES, deprecated=True)
async def get_user_report(user_id: str, http_request: Request):
    verify_resource_ownership(http_request, user_id)

    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    report = report_response(snapshot)

    audit_logger = get_audit_logger()
    audit_logger.log_access(
        user_id=user_id,
        resource_type="report",
        resource_id=user_id,
        action="view_report",
        ip_address=http_request.client.host if http_request.client else "",
    )
    return report


@router.get("/{user_id}/recommendations", response_model=ProfileRecommendationsResponse, responses=STUDENT_API_RESPONSES, deprecated=True)
async def get_recommendations(user_id: str, http_request: Request):
    verify_resource_ownership(http_request, user_id)

    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    return {
        "user_id": user_id,
        "recommendations": snapshot.recommendations,
    }


@router.put("/{user_id}/preferences", response_model=PreferencesUpdateResponse, responses=STUDENT_API_RESPONSES, deprecated=True)
async def update_preferences(
    user_id: str,
    preferences: PreferencesUpdateRequest,
    http_request: Request,
):
    verify_resource_ownership(http_request, user_id)
    return await _apply_preferences(user_id, preferences, http_request)


@router.get("/{user_id}/skills", response_model=SkillProfileResponse, responses=STUDENT_API_RESPONSES, deprecated=True)
async def get_user_skill_profile(user_id: str, http_request: Request):
    verify_resource_ownership(http_request, user_id)
    return await _build_skill_profile_response(user_id)


# ========================================================================
# 共享实现
# ========================================================================


async def _apply_preferences(
    user_id: str,
    preferences: PreferencesUpdateRequest,
    http_request: Request,
) -> dict:
    try:
        async with get_db_session() as db:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(user_id)

            if user is None:
                raise HTTPException(status_code=404, detail="用户不存在")

            current_prefs = user.preferences or {}

            update_data = preferences.model_dump(exclude_none=True)
            current_prefs.update(update_data)

            await user_repo.update(user_id, preferences=current_prefs)

        audit_logger = get_audit_logger()
        audit_logger.log_modification(
            user_id=user_id,
            resource_type="preferences",
            resource_id=user_id,
            old_value={},
            new_value=current_prefs,
            changed_fields=list(update_data.keys()),
        )

        # 偏好变更影响画像 → 使快照缓存失效
        from agent_core.memory_persistence import MemoryPersistenceFacade
        facade = MemoryPersistenceFacade()
        await facade.invalidate_profile_snapshot(user_id)

        return {
            "success": True,
            "message": "偏好设置已更新",
            "preferences": current_prefs,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"更新偏好设置失败: {str(e)}"
        )


async def _build_skill_profile_response(user_id: str) -> dict:
    """技能画像响应（复用统一快照的技能数据 + SkillAggregator/DAG 扩展）。"""
    try:
        from app.services.skill_aggregator import SkillAggregator
        from app.services.difficulty_estimator import DifficultyEstimator
        from app.services.math_skill_dag import MathSkillDAG

        facade = await _get_facade()
        snapshot = await facade.get_profile_snapshot(user_id)
        skills = snapshot.skills
        error_patterns = snapshot.error_pattern_list or await SkillAggregator().get_error_patterns(user_id)
        cognitive_style = snapshot.cognitive_style or await SkillAggregator().get_cognitive_style(user_id)

        dag = MathSkillDAG()
        mastered_codes = {
            s["skill_code"] for s in skills if s["status"] == "mastered"
        }
        learning_codes = {s["skill_code"] for s in skills}
        next_unlockable = dag.get_next_unlockable(mastered_codes, learning_codes)

        est = DifficultyEstimator()
        difficulty_by_category = {}
        for cat in set(s.get("category_path", "").split(" > ")[0] for s in skills if s.get("category_path")):
            if cat:
                d = await est.estimate(user_id, cat)
                difficulty_by_category[cat] = d

        return {
            "user_id": user_id,
            "generated_at": snapshot.generated_at,
            "skill_summary": {
                "total_skills": len(skills),
                "mastered": sum(1 for s in skills if s["status"] == "mastered"),
                "proficient": sum(1 for s in skills if s["status"] == "proficient"),
                "learning": sum(1 for s in skills if s["status"] == "learning"),
                "novice": sum(1 for s in skills if s["status"] == "novice"),
            },
            "skills": [
                {
                    "code": s["skill_code"],
                    "name": s.get("display_name", ""),
                    "category": s.get("category_path", ""),
                    "mastery": round(s["mastery_level"], 3),
                    "mastery_score": s.get("mastery_score", s["mastery_level"]),
                    "evidence_count": s.get("evidence_count", 0),
                    "confidence_level": s.get("confidence_level", "insufficient"),
                    "status": s["status"],
                    "attempts": s.get("total_attempts", 0),
                    "correct": s.get("correct_count", 0),
                    "streak": {"current": s.get("recent_streak", 0), "best": s.get("best_streak", 0)},
                }
                for s in sorted(skills, key=lambda x: x["mastery_level"], reverse=True)
            ],
            "error_patterns": error_patterns,
            "cognitive_style": cognitive_style,
            "next_recommended_skills": [
                {"code": n["code"], "name": n["node"].get("display_name", ""), "prerequisites": n["node"].get("prerequisites", [])}
                for n in next_unlockable[:5]
            ],
            "difficulty_estimate_by_category": difficulty_by_category,
            "compact_profile": snapshot.to_compact_json(max_length=1200),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取技能画像失败: {str(e)}"
        )


@router.post("/track", response_model=TrackLearningResponse, responses=STUDENT_API_RESPONSES)
async def track_learning_behavior(
    request: Request,
    body: TrackLearningRequest,
):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")

    try:
        from app.services.behavior_tracker import LearningBehaviorTracker
        from agent_core.memory_persistence import MemoryPersistenceFacade

        tracker = LearningBehaviorTracker()
        tracked = tracker.track(
            user_id=user_id,
            raw_input=body.content or body.question_content,
            source=body.source,
            metadata=body.metadata,
        )

        facade = MemoryPersistenceFacade()
        success = await facade.record_event(user_id, tracked)

        return {
            "success": True,
            "tracked_event": {
                "event_type": tracked.get("event_type"),
                "category": tracked.get("category"),
                "sub_categories": tracked.get("sub_categories"),
                "source": tracked.get("source"),
            },
            "persisted": success,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"行为追踪记录失败: {str(e)}"
        )
