from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.data.database import get_db_session
from app.data.repositories import UserRepository
from app.services.profile_analyzer import UserProfileAnalyzer
from app.services.cache import get_cache_manager
from app.security.audit import get_audit_logger
from app.security.access_control import verify_resource_ownership

router = APIRouter(prefix="/api/profile", tags=["用户画像"])


class PreferencesUpdateRequest(BaseModel):
    difficulty_mode: Optional[str] = Field(None, description="难度模式: adaptive | fixed")
    preferred_categories: Optional[list[str]] = None
    daily_goal_minutes: Optional[int] = Field(None, ge=5, le=240)


@router.get("/{user_id}")
async def get_user_profile(
    user_id: str,
    http_request: Request,
    include_recommendations: bool = Query(False),
    include_history: bool = Query(False),
):
    verify_resource_ownership(http_request, user_id)

    cache = get_cache_manager()
    cache_key = f"user:profile:{user_id}:{include_recommendations}"

    if not include_history:
        cached = await cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        analyzer = UserProfileAnalyzer(get_db_session)
        profile = await analyzer.analyze(user_id)

        profile["user_id"] = user_id

        summary = {
            "total_questions": profile.get("total_questions", 0),
            "correct_rate": profile.get("correct_rate", 0),
            "avg_time_per_question": profile.get("avg_time_per_question", 0),
        }
        if summary["correct_rate"] > 0.85:
            summary["learning_level"] = "expert"
        elif summary["correct_rate"] > 0.7:
            summary["learning_level"] = "advanced"
        elif summary["correct_rate"] > 0.5:
            summary["learning_level"] = "intermediate"
        elif summary["correct_rate"] > 0.3:
            summary["learning_level"] = "elementary"
        else:
            summary["learning_level"] = "beginner"

        weak_points = profile.pop("weak_points", [])
        strong_points = profile.pop("strong_points", [])
        capabilities = {wp["category"]: wp["mastery"] for wp in weak_points}
        for sp in strong_points:
            capabilities[sp] = 0.9

        response = {
            "user_id": user_id,
            "generated_at": profile.get(
                "generated_at",
                __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
            ),
            "summary": summary,
            "capability": {
                "knowledge_mastery": capabilities,
                "recommended_difficulty": profile.get(
                    "recommended_difficulty", 3
                ),
            },
            "behavior": profile.get("behavior", {}),
            "error_patterns": profile.get("error_patterns", {}),
            "progress_trends": profile.get("progress_trends", {}),
            "preferences": profile.get("preferences", {}),
        }

        if include_recommendations:
            response["recommendations"] = profile.get("recommendations", [])

        if not include_history:
            await cache.set(cache_key, response, ttl=600)

        audit_logger = get_audit_logger()
        audit_logger.log_access(
            user_id=user_id,
            resource_type="profile",
            resource_id=user_id,
            action="view_profile",
            ip_address=http_request.client.host
            if http_request.client
            else "",
        )

        return response

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取用户画像失败: {str(e)}"
        )


@router.get("/{user_id}/report")
async def get_user_report(user_id: str, http_request: Request):
    verify_resource_ownership(http_request, user_id)

    try:
        analyzer = UserProfileAnalyzer(get_db_session)
        profile = await analyzer.analyze(user_id)

        report = {
            "user_id": user_id,
            "generated_at": __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .isoformat(),
            "overview": {
                "total_questions": profile.get("total_questions", 0),
                "correct_rate": profile.get("correct_rate", 0),
                "avg_time_per_question": profile.get("avg_time_per_question", 0),
                "recommended_difficulty": profile.get(
                    "recommended_difficulty", 3
                ),
            },
            "weak_points": profile.get("weak_points", []),
            "strong_points": profile.get("strong_points", []),
            "error_patterns": profile.get("error_patterns", {}),
            "progress_trends": profile.get("progress_trends", {}),
            "recommendations": profile.get("recommendations", []),
        }

        audit_logger = get_audit_logger()
        audit_logger.log_access(
            user_id=user_id,
            resource_type="report",
            resource_id=user_id,
            action="view_report",
            ip_address=http_request.client.host
            if http_request.client
            else "",
        )

        return report

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"生成学习报告失败: {str(e)}"
        )


@router.get("/{user_id}/recommendations")
async def get_recommendations(user_id: str, http_request: Request):
    verify_resource_ownership(http_request, user_id)

    try:
        analyzer = UserProfileAnalyzer(get_db_session)
        profile = await analyzer.analyze(user_id)

        return {
            "user_id": user_id,
            "recommendations": profile.get("recommendations", []),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取推荐建议失败: {str(e)}"
        )


@router.put("/{user_id}/preferences")
async def update_preferences(
    user_id: str,
    preferences: PreferencesUpdateRequest,
    http_request: Request,
):
    verify_resource_ownership(http_request, user_id)

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

        cache = get_cache_manager()
        await cache.invalidate_pattern(f"user:profile:{user_id}*")

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