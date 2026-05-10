from tools.vision_tool import VisionTool
from tools import get_registry, ToolNotFoundError
from agent_core import MathAgent
from error_book import ErrorBookManager, ErrorItem
from data_processing.validators import ErrorBookValidator
from data_processing.formatters import ErrorBookFormatter
import asyncio
import logging
import os
import base64
import json
import time
import traceback
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from app.config.settings import settings
from app.middleware.auth import (
    verify_access_token,
    init_default_admin,
    create_token_pair,
)
from app.middleware.security import (
    validate_input,
    validate_request_data,
    is_safe_image_data,
    SecurityValidationError,
)

logger = logging.getLogger(__name__)
from app.api.auth import router as auth_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=settings.CORS_MAX_AGE,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self' https://dashscope.aliyuncs.com; "
        "frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = settings.RATE_LIMIT_PER_MINUTE


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/static") or request.url.path in ["/", "/error_book"]:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    requests = _rate_limit_store[client_ip]
    requests[:] = [t for t in requests if now - t < RATE_LIMIT_WINDOW]

    if len(requests) >= RATE_LIMIT_MAX:
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
        )

    requests.append(now)
    return await call_next(request)


NO_AUTH_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/chat",
    "/api/chat/react",
    "/api/chat/multimodal",
    "/api/recognize",
    "/api/error-book",
    "/api/tools",
    "/api/tools/stats",
    "/api/tools/search",
    "/api/tools/",
    "/api/agent/thought/",
    "/api/agent/stats",
    "/",
    "/error_book",
    "/docs",
    "/redoc",
    "/openapi.json",
}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if path in NO_AUTH_PATHS or path.startswith("/static") or path.startswith("/assets") or path.startswith("/@vite") or path.startswith("/api/auth"):
        return await call_next(request)

    if request.method == "OPTIONS":
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "未提供认证令牌，请先登录"},
        )

    token = auth_header[7:]
    user_id = verify_access_token(token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)

    if user_id is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "认证令牌无效或已过期，请重新登录"},
        )

    request.state.user_id = user_id
    return await call_next(request)


app.include_router(auth_router)


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


class ErrorItemRequest(BaseModel):
    id: str = ""
    question: str
    question_type: str = "text"
    image_path: str | None = None
    error_reason: str = ""
    categories: list[str] = []
    original_answer: str = ""
    correct_answer: str = ""
    notes: str = ""
    added_at: str = ""
    mastery_level: int = 3
    is_mastered: bool = False


class ErrorUpdateRequest(BaseModel):
    question: str | None = None
    question_type: str | None = None
    image_path: str | None = None
    error_reason: str | None = None
    categories: list[str] | None = None
    original_answer: str | None = None
    correct_answer: str | None = None
    notes: str | None = None
    added_at: str | None = None
    mastery_level: int | None = None
    is_mastered: bool | None = None


api_key = settings.DASHSCOPE_API_KEY

registry = get_registry()
agent = MathAgent(api_key=api_key, registry=registry)

error_book_manager = ErrorBookManager()

init_default_admin(settings.JWT_SECRET_KEY)


async def _stream_agent_response(message, session_id, context_label="聊天"):
    """统一的 Agent 流式响应生成器。直接转发 agent.stream() 的每个 chunk。"""
    try:
        async for chunk in agent.stream(message, session_id=session_id):
            if chunk:
                if not isinstance(chunk, str):
                    chunk = str(chunk)
                try:
                    yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"
                except (TypeError, ValueError) as json_error:
                    yield f"data: {json.dumps({'content': f'JSON序列化错误: {str(json_error)}', 'type': 'error'})}\n\n"

        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"流式{context_label}失败: {e}\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'content': '服务器内部错误', 'type': 'error'})}\n\n"
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"


async def stream_recognize_response(image_data, session_id):
    """
    流式响应图片识别结果（性能优化版）。

    优化点：
    1. 降低提示信息延迟
    2. 快速进入核心处理流程
    """
    try:
        if image_data.startswith("data:image/"):
            image_data = image_data.split(",")[1]

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_file.write(base64.b64decode(image_data))
            temp_file_path = temp_file.name

        try:
            start_msg = "**【正在识别图片内容...】**\n\n"
            yield f"data: {json.dumps({'content': start_msg, 'type': 'status'})}\n\n"

            async for chunk in agent.stream(temp_file_path, session_id=session_id):
                if chunk:
                    if not isinstance(chunk, str):
                        chunk = str(chunk)
                    yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"

            yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    except Exception as e:
        logger.error(f"图片识别流式处理失败: {e}\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'content': '服务器内部错误', 'type': 'error'})}\n\n"
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"


async def stream_multimodal_response(message, image_data, session_id):
    """
    流式响应多模态输入（图片+文字）。

    将图片和文字合并后一起发送给Agent处理，确保AI能获得完整上下文。
    """
    try:
        if image_data:
            if image_data.startswith("data:image/"):
                image_data = image_data.split(",")[1]

            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_file.write(base64.b64decode(image_data))
                temp_file_path = temp_file.name

            try:
                start_msg = "**【正在识别图片内容...】**\n\n"
                yield f"data: {json.dumps({'content': start_msg, 'type': 'status'})}\n\n"

                async for chunk in agent.stream_multimodal(temp_file_path, message, session_id=session_id):
                    if chunk:
                        if not isinstance(chunk, str):
                            chunk = str(chunk)
                        yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"

                yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        else:
            async for chunk in agent.stream(message, session_id=session_id):
                if chunk:
                    if not isinstance(chunk, str):
                        chunk = str(chunk)
                    yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"

            yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"多模态流式处理失败: {e}\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'content': '服务器内部错误', 'type': 'error'})}\n\n"
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"


@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request):
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
        _stream_agent_response(validated_message, validated_session),
        media_type="text/event-stream",
    )



@app.post("/api/chat/react")
async def chat_react(request: ChatRequest, http_request: Request):
    """
    ReAct Agent 聊天接口（已废弃，向后兼容）。

    .. deprecated::
        此端点与 /api/chat 功能完全重复，仅保留用于向后兼容。
        新代码请使用 /api/chat。
    """
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
        _stream_agent_response(validated_message, validated_session, "React"),
        media_type="text/event-stream",
    )


@app.get("/api/agent/thought/{session_id}")
async def get_thought_history(session_id: str):
    """获取指定会话的 ReAct 思维过程历史。"""
    recorder = agent.get_thought_recorder()
    processes = recorder.get_session_processes(session_id, limit=10)
    return {
        "session_id": session_id,
        "processes": [p.to_dict() for p in processes],
        "total": len(processes),
    }


@app.get("/api/agent/stats")
async def get_agent_stats():
    """获取 Agent 统计信息。"""
    recorder = agent.get_thought_recorder()
    return recorder.get_stats()


@app.post("/api/recognize")
async def recognize(request: RecognizeRequest, http_request: Request):
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
        stream_recognize_response(request.image, validated_session),
        media_type="text/event-stream",
    )


@app.post("/api/chat/multimodal")
async def chat_multimodal(request: MultimodalChatRequest, http_request: Request):
    """
    多模态聊天接口（支持图片+文字同时输入）。

    将图片和文字作为一个完整的请求发送给Agent处理，
    确保AI能够获得完整的上下文信息。
    """
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
        stream_multimodal_response(validated_message, request.image, validated_session),
        media_type="text/event-stream",
    )


@app.get("/api/error-book")
def get_error_book():
    try:
        errors = error_book_manager.get_all()
        return [error.to_dict() for error in errors]
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@app.post("/api/error-book")
def add_error(request: ErrorItemRequest):
    try:
        raw_data = request.dict()
        try:
            validated_data = validate_request_data(raw_data, max_length=settings.INPUT_MAX_LENGTH, skip_sql_check=True)
        except SecurityValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        is_valid, validation_errors = ErrorBookValidator.validate(validated_data)

        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"数据验证失败: {'; '.join(validation_errors)}",
            )

        formatted_data = ErrorBookFormatter.format(validated_data)

        error_item = ErrorItem(
            id=formatted_data.get("id", ""),
            question=formatted_data.get("question", ""),
            question_type=formatted_data.get("question_type", "text"),
            image_path=formatted_data.get("image_path"),
            error_reason=formatted_data.get("error_reason", ""),
            categories=formatted_data.get("categories", []),
            original_answer=formatted_data.get("original_answer", ""),
            correct_answer=formatted_data.get("correct_answer", ""),
            notes=formatted_data.get("notes", ""),
            added_at=formatted_data.get("added_at", ""),
            mastery_level=formatted_data.get("mastery_level", 3),
            is_mastered=formatted_data.get("is_mastered", False),
        )

        error_id = error_book_manager.add(error_item)

        return {
            "id": error_id,
            "status": "success",
            "message": "错题添加成功",
            "data": {
                **error_item.to_dict(),
                "display_question": formatted_data.get("display_question", ""),
                "recognized_text": formatted_data.get("recognized_text", ""),
                "answer_preview": formatted_data.get("answer_preview", ""),
                "has_image": formatted_data.get("has_image", False),
                "categories": formatted_data.get("categories", []),
            },
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@app.put("/api/error-book/{error_id}")
def update_error(error_id: str, request: ErrorUpdateRequest):
    try:
        try:
            validated_id = validate_input(error_id, "error_id", max_length=64)
        except SecurityValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        update_data = {}
        fields = [
            "question", "question_type", "image_path", "error_reason",
            "categories", "original_answer", "correct_answer", "notes",
            "added_at", "mastery_level", "is_mastered",
        ]
        for field in fields:
            value = getattr(request, field, None)
            if value is not None:
                try:
                    update_data[field] = validate_input(value, field, max_length=settings.INPUT_MAX_LENGTH)
                except SecurityValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

        success = error_book_manager.update(validated_id, **update_data)
        return {"success": success}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@app.delete("/api/error-book/{error_id}")
def delete_error(error_id: str):
    try:
        validated_id = validate_input(error_id, "error_id", max_length=64)
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        success = error_book_manager.remove(validated_id)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@app.exception_handler(SecurityValidationError)
async def security_validation_handler(request: Request, exc: SecurityValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "threat_type": exc.threat_type},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


@app.get("/api/tools")
async def list_tools():
    """返回所有已注册工具的完整信息列表。"""
    tools = registry.list_tools()
    return {"tools": tools, "total": len(tools)}


@app.get("/api/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """返回指定工具的完整信息。"""
    try:
        tool = registry.get_tool(tool_name)
        return tool.get_info()
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"工具未注册: '{tool_name}'")


@app.get("/api/tools/stats")
async def get_tool_stats():
    """返回工具执行统计信息。"""
    return registry.get_execution_stats()


@app.get("/api/tools/search")
async def search_tools(capability: str):
    """按能力标签搜索已注册的工具。"""
    tools = registry.search_tools(capability)
    return {"capability": capability, "tools": tools}


if not os.path.exists("static"):
    os.makedirs("static")

if not os.path.exists("frontend/dist"):
    os.makedirs("frontend/dist")

if not os.path.exists("frontend/dist/assets"):
    os.makedirs("frontend/dist/assets")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")


@app.get("/")
def index():
    return FileResponse("frontend/dist/index.html")


@app.get("/error_book")
def error_book():
    return FileResponse("frontend/dist/index.html")


if __name__ == "__main__":
    if not os.path.exists("static"):
        os.makedirs("static")

    print("\n服务器启动中...")
    print("访问地址: http://localhost:8000")
    print("API文档: http://localhost:8000/docs")
    print("\n[安全] CORS已限制为:", settings.CORS_ORIGINS)
    print("[安全] JWT认证已启用")
    print("[安全] 输入过滤已启用")
    print("[安全] 速率限制: {}次/分钟".format(settings.RATE_LIMIT_PER_MINUTE))

    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
