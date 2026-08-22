from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.data.database import get_db_session
from app.data.repositories import UserRepository
from app.services.profile_application import ProfileSnapshot
from app.security.audit import get_audit_logger
from app.security.access_control import verify_resource_ownership

router = APIRouter(prefix="/api/profile", tags=["用户画像"])


class PreferencesUpdateRequest(BaseModel):
    difficulty_mode: Optional[str] = Field(None, description="难度模式: adaptive | fixed")
    preferred_categories: Optional[list[str]] = None
    daily_goal_minutes: Optional[int] = Field(None, ge=5, le=240)


def _current_user(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return user_id


async def _get_facade():
    from agent_core.memory_persistence import MemoryPersistenceFacade
    return MemoryPersistenceFacade()


def _snapshot_to_profile_response(
    snapshot: ProfileSnapshot,
    include_recommendations: bool = False,
) -> dict:
    """将统一快照转换为旧版 /profile/{user_id} 响应结构（契约不变）。"""
    summary = {
        "total_questions": snapshot.total_questions,
        "correct_rate": snapshot.correct_rate,
        "avg_time_per_question": snapshot.avg_time_per_question,
        "learning_level": snapshot.get_learning_level(),
    }

    capabilities = {
        wp["category"]: wp["mastery"] for wp in snapshot.weak_points
    }
    for sp in snapshot.strong_points:
        capabilities[sp] = 0.9

    response = {
        "user_id": snapshot.user_id,
        "generated_at": snapshot.generated_at,
        "summary": summary,
        "capability": {
            "knowledge_mastery": capabilities,
            "recommended_difficulty": snapshot.recommended_difficulty,
        },
        "behavior": snapshot.behavior,
        "error_patterns": snapshot.error_patterns,
        "progress_trends": snapshot.progress_trends,
        "preferences": snapshot.preferences,
    }

    if include_recommendations:
        response["recommendations"] = snapshot.recommendations

    return response


def _snapshot_to_report(snapshot: ProfileSnapshot) -> dict:
    """将统一快照转换为旧版 /report 响应结构（契约不变）。"""
    return {
        "user_id": snapshot.user_id,
        "generated_at": snapshot.generated_at,
        "overview": {
            "total_questions": snapshot.total_questions,
            "correct_rate": snapshot.correct_rate,
            "avg_time_per_question": snapshot.avg_time_per_question,
            "recommended_difficulty": snapshot.recommended_difficulty,
        },
        "weak_points": snapshot.weak_points,
        "strong_points": snapshot.strong_points,
        "error_patterns": snapshot.error_patterns,
        "progress_trends": snapshot.progress_trends,
        "recommendations": snapshot.recommendations,
    }


# ========================================================================
# /me 系列：一律从认证上下文取 user_id，不接受 path user_id
# ========================================================================


@router.get("/me")
async def get_my_profile(
    http_request: Request,
    include_recommendations: bool = Query(False),
    include_history: bool = Query(False),
):
    user_id = _current_user(http_request)
    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    response = _snapshot_to_profile_response(
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


@router.get("/me/report")
async def get_my_report(http_request: Request):
    user_id = _current_user(http_request)
    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    report = _snapshot_to_report(snapshot)

    audit_logger = get_audit_logger()
    audit_logger.log_access(
        user_id=user_id,
        resource_type="report",
        resource_id=user_id,
        action="view_report",
        ip_address=http_request.client.host if http_request.client else "",
    )
    return report


@router.get("/me/recommendations")
async def get_my_recommendations(http_request: Request):
    user_id = _current_user(http_request)
    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)
    return {
        "user_id": user_id,
        "recommendations": snapshot.recommendations,
    }


@router.get("/me/skills")
async def get_my_skill_profile(http_request: Request):
    user_id = _current_user(http_request)
    return await _build_skill_profile_response(user_id)


@router.put("/me/preferences")
async def update_my_preferences(
    preferences: PreferencesUpdateRequest,
    http_request: Request,
):
    user_id = _current_user(http_request)
    return await _apply_preferences(user_id, preferences, http_request)


# ========================================================================
# 旧路由：保留兼容，校验 ownership 后转发到统一快照实现
# ========================================================================


@router.get("/{user_id}")
async def get_user_profile(
    user_id: str,
    http_request: Request,
    include_recommendations: bool = Query(False),
    include_history: bool = Query(False),
):
    verify_resource_ownership(http_request, user_id)

    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    response = _snapshot_to_profile_response(
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


@router.get("/{user_id}/report")
async def get_user_report(user_id: str, http_request: Request):
    verify_resource_ownership(http_request, user_id)

    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    report = _snapshot_to_report(snapshot)

    audit_logger = get_audit_logger()
    audit_logger.log_access(
        user_id=user_id,
        resource_type="report",
        resource_id=user_id,
        action="view_report",
        ip_address=http_request.client.host if http_request.client else "",
    )
    return report


@router.get("/{user_id}/recommendations")
async def get_recommendations(user_id: str, http_request: Request):
    verify_resource_ownership(http_request, user_id)

    facade = await _get_facade()
    snapshot = await facade.get_profile_snapshot(user_id)

    return {
        "user_id": user_id,
        "recommendations": snapshot.recommendations,
    }


@router.put("/{user_id}/preferences")
async def update_preferences(
    user_id: str,
    preferences: PreferencesUpdateRequest,
    http_request: Request,
):
    verify_resource_ownership(http_request, user_id)
    return await _apply_preferences(user_id, preferences, http_request)


@router.get("/{user_id}/skills")
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


@router.post("/track")
async def track_learning_behavior(
    request: Request,
    body: dict,
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
            raw_input=body.get("content", "") or body.get("question_content", ""),
            source=body.get("source", "api"),
            metadata=body.get("metadata", {}),
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
