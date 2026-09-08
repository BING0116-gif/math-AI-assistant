"""
聊天相关 API 路由。

包含 /api/chat, /api/chat/react, /api/chat/multimodal, /api/recognize 端点。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal

from app.config.settings import settings
from app.middleware.security import (
    validate_input,
    is_safe_image_data,
    SecurityValidationError,
)
from app.models.ai_unavailable import AIUnavailableResponse
from app.services.ai_capability import get_ai_capability, is_ai_available
from app.services.stream_handler import (
    stream_agent_response,
    stream_recognize_response,
    stream_multimodal_response,
)

router = APIRouter(tags=["chat"])


class TutorContextRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    course_id: str | None = Field(default=None, max_length=36)
    version_id: str | None = Field(default=None, max_length=36)
    knowledge_point_codes: list[str] = Field(default_factory=list, max_length=20)
    source_session_id: str | None = Field(default=None, max_length=36)
    question_id: str | None = Field(default=None, max_length=20)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    tutor_mode: Literal["hint_only", "step_by_step", "check_my_work"] = "step_by_step"
    context: TutorContextRequest = Field(default_factory=TutorContextRequest)


class RecognizeRequest(BaseModel):
    image: str
    session_id: str = "default"


class MultimodalChatRequest(BaseModel):
    message: str = ""
    image: str | None = None
    session_id: str = "default"
    tutor_mode: Literal["hint_only", "step_by_step", "check_my_work"] = "step_by_step"
    context: TutorContextRequest = Field(default_factory=TutorContextRequest)


class UpdateChatSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    default_tutor_mode: Literal["hint_only", "step_by_step", "check_my_work"] | None = None
    archive: bool = False


def _user_id(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not value: raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(value)


async def _tutor_run(http_request: Request, session_id: str, mode: str, context: dict[str, Any], message: str = ""):
    from app.services.tutor_service import resolve_tutor_context, start_ai_run
    user_id = _user_id(http_request)
    clean_context = context.model_dump(exclude_none=True) if isinstance(context, BaseModel) else context
    try: resolved, internal_id = await resolve_tutor_context(user_id, session_id, mode, clean_context, query=message)
    except PermissionError as error: raise HTTPException(status_code=403, detail={"code": "TUTOR_CONTEXT_FORBIDDEN", "message": str(error)})
    return user_id, resolved, await start_ai_run(user_id, internal_id, mode, resolved)


def _check_ai_available(capability: str) -> None:
    """检查 AI 是否可用，不可用时抛出 HTTPException。"""
    if not is_ai_available():
        cap = get_ai_capability()
        resp = AIUnavailableResponse.for_capability(capability, cap.reason)
        raise HTTPException(
            status_code=503,
            detail=resp.model_dump(),
        )


def get_agent():
    """获取全局 Agent 实例。"""
    from app.dependencies import get_agent as _get_agent
    return _get_agent()


@router.post("/api/chat", responses={
    503: {"description": "AI 功能不可用", "model": AIUnavailableResponse},
})
async def chat(request: ChatRequest, http_request: Request):
    _check_ai_available("chat")

    try:
        validated_message = validate_input(
            request.message, "message", max_length=settings.INPUT_MAX_LENGTH
        )
        validated_session = validate_input(
            request.session_id, "session_id", max_length=128
        )
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not validated_message:
        raise HTTPException(status_code=400, detail="请输入消息")

    user_id, tutor_context, run_id = await _tutor_run(http_request, validated_session, request.tutor_mode, request.context, validated_message)
    return StreamingResponse(
        stream_agent_response(
            get_agent(),
            validated_message, validated_session,
            user_id=user_id, tutor_mode=request.tutor_mode, tutor_context=tutor_context, ai_run_id=run_id,
        ),
        media_type="text/event-stream",
    )


@router.post("/api/chat/react", include_in_schema=False, deprecated=True, responses={
    503: {"description": "AI 功能不可用", "model": AIUnavailableResponse},
})
async def chat_react(request: ChatRequest, http_request: Request):
    _check_ai_available("chat")

    try:
        validated_message = validate_input(
            request.message, "message", max_length=settings.INPUT_MAX_LENGTH
        )
        validated_session = validate_input(
            request.session_id, "session_id", max_length=128
        )
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not validated_message:
        raise HTTPException(status_code=400, detail="请输入消息")

    user_id, tutor_context, run_id = await _tutor_run(http_request, validated_session, request.tutor_mode, request.context, validated_message)
    return StreamingResponse(
        stream_agent_response(
            get_agent(),
            validated_message, validated_session, "React",
            user_id=user_id, tutor_mode=request.tutor_mode, tutor_context=tutor_context, ai_run_id=run_id,
        ),
        media_type="text/event-stream",
    )


@router.post("/api/recognize", responses={
    503: {"description": "AI 功能不可用", "model": AIUnavailableResponse},
})
async def recognize(request: RecognizeRequest, http_request: Request):
    _check_ai_available("recognize")

    try:
        if not is_safe_image_data(request.image):
            raise SecurityValidationError("图片数据格式不合法", "invalid_image")
        validated_session = validate_input(
            request.session_id, "session_id", max_length=128
        )
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not request.image:
        raise HTTPException(status_code=400, detail="请提供图片数据")

    return StreamingResponse(
        stream_recognize_response(
            get_agent(),
            request.image,
            validated_session,
            user_id=str(http_request.state.user_id),
        ),
        media_type="text/event-stream",
    )


@router.post("/api/chat/multimodal", responses={
    503: {"description": "AI 功能不可用", "model": AIUnavailableResponse},
})
async def chat_multimodal(request: MultimodalChatRequest, http_request: Request):
    _check_ai_available("multimodal")

    try:
        validated_message = validate_input(
            request.message, "message", max_length=settings.INPUT_MAX_LENGTH
        ) if request.message else ""
        validated_session = validate_input(
            request.session_id, "session_id", max_length=128
        )
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not request.image and not validated_message:
        raise HTTPException(status_code=400, detail="请提供图片或文字内容")

    if request.image and not is_safe_image_data(request.image):
        raise HTTPException(status_code=400, detail="图片数据格式不合法")

    user_id, tutor_context, run_id = await _tutor_run(http_request, validated_session, request.tutor_mode, request.context, validated_message)
    return StreamingResponse(
        stream_multimodal_response(
            get_agent(),
            validated_message, request.image, validated_session,
            user_id=user_id, tutor_mode=request.tutor_mode, tutor_context=tutor_context, ai_run_id=run_id,
        ),
        media_type="text/event-stream",
    )


@router.get("/api/chat/sessions")
async def list_chat_sessions(http_request: Request):
    from app.services.memory_application import MemoryApplicationService
    return {"code": 0, "data": await MemoryApplicationService().list_chat_sessions(_user_id(http_request))}


@router.get("/api/chat/sessions/{session_id}")
async def get_chat_session(session_id: str, http_request: Request):
    from app.services.memory_application import MemoryApplicationService
    data = await MemoryApplicationService().get_chat_session(_user_id(http_request), session_id)
    if data is None: raise HTTPException(status_code=404, detail={"code": "CHAT_SESSION_NOT_FOUND", "message": "对话不存在"})
    return {"code": 0, "data": data}


@router.patch("/api/chat/sessions/{session_id}")
async def update_chat_session(session_id: str, body: UpdateChatSessionRequest, http_request: Request):
    from app.services.memory_application import MemoryApplicationService
    try: data = await MemoryApplicationService().update_chat_session(_user_id(http_request), session_id, title=body.title, default_tutor_mode=body.default_tutor_mode, archive=body.archive)
    except LookupError: raise HTTPException(status_code=404, detail={"code": "CHAT_SESSION_NOT_FOUND", "message": "对话不存在"})
    return {"code": 0, "data": data}
