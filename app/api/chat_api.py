"""
聊天相关 API 路由。

包含 /api/chat, /api/chat/react, /api/chat/multimodal, /api/recognize 端点。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

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


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class RecognizeRequest(BaseModel):
    image: str
    session_id: str = "default"


class MultimodalChatRequest(BaseModel):
    message: str = ""
    image: str | None = None
    session_id: str = "default"


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

    return StreamingResponse(
        stream_agent_response(
            get_agent(),
            validated_message, validated_session,
            user_id=getattr(http_request.state, "user_id", None),
        ),
        media_type="text/event-stream",
    )


@router.post("/api/chat/react", responses={
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

    return StreamingResponse(
        stream_agent_response(
            get_agent(),
            validated_message, validated_session, "React",
            user_id=getattr(http_request.state, "user_id", None),
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

    return StreamingResponse(
        stream_multimodal_response(
            get_agent(),
            validated_message, request.image, validated_session,
            user_id=getattr(http_request.state, "user_id", None),
        ),
        media_type="text/event-stream",
    )