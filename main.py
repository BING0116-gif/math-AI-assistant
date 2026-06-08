from tools.vision_tool import VisionTool
from tools import get_registry, ToolNotFoundError
from agent_core import MathAgent
from error_book import ErrorBookManager, ErrorItem
from data_processing.validators import ErrorBookValidator
from data_processing.formatters import ErrorBookFormatter
from prompts.dynamic_params import init_dynamic_llm_factory
import asyncio
import logging
import os
import sys
import base64
import json
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
import re as _re
from app.config.settings import settings
from app.config.middleware_config import middleware_config
from app.middleware.auth import (
    init_default_admin,
    create_token_pair,
)
from app.middleware.security import (
    validate_input,
    validate_request_data,
    is_safe_image_data,
    SecurityValidationError,
)
from app.middleware.path_matcher import PathMatcher
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.auth_middleware import AuthenticationMiddleware
from app.api.auth import router as auth_router
from app.api.memory_api import router as memory_router
from app.api.profile_api import router as profile_router
from app.api.data_api import router as data_router
from app.api.recommendation_api import router as recommendation_router
from app.data.database import init_db, close_db, check_database_health
from app.services.cache import get_cache_manager
from app.security.encryption import get_encryption
from app.security.audit import get_audit_logger

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-6s | %(name)-30s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,  # 强制覆盖uvicorn的日志配置，确保所有模块日志都能输出
    handlers=[logging.StreamHandler(sys.stdout)],  # 确保输出到stdout
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("正在初始化数据库...")
    await init_db()
    logger.info("数据库初始化完成")

    # ── RAG 推荐系统初始化 ──
    if settings.RAG_ENABLED:
        try:
            if settings.RAG_ENABLE_VECTOR_SEARCH:
                from app.services.vector_store import get_vector_store
                await get_vector_store()
                logger.info("向量数据库初始化完成")
        except Exception as e:
            logger.warning(f"向量数据库初始化失败: {e}")
        try:
            if settings.RAG_ENABLE_AI_EXPLANATION:
                from app.services.llm_service import get_llm_service
                get_llm_service()
                logger.info("LLM服务初始化完成")
        except Exception as e:
            logger.warning(f"LLM服务初始化失败: {e}")
    # ── END RAG ──

    cache_mgr = get_cache_manager()
    redis_url = settings.REDIS_URL
    if redis_url:
        await cache_mgr.initialize()

    logger.info("应用启动完成")
    yield

    logger.info("正在关闭连接...")
    await cache_mgr.close()
    await close_db()
    logger.info("连接已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Session-Id"],
    max_age=settings.CORS_MAX_AGE,
)


path_matcher = PathMatcher(
    static_paths=middleware_config.STATIC_PATHS,
    skip_paths=list(middleware_config.NO_AUTH_PATHS),
)

app.add_middleware(
    SecurityHeadersMiddleware,
    debug=settings.DEBUG,
)

app.add_middleware(
    RateLimitMiddleware,
    window_seconds=middleware_config.RATE_LIMIT_WINDOW_SECONDS,
    max_requests=middleware_config.RATE_LIMIT_MAX_REQUESTS,
    path_matcher=path_matcher,
)

app.add_middleware(
    AuthenticationMiddleware,
    jwt_secret_key=settings.JWT_SECRET_KEY,
    jwt_algorithm=settings.JWT_ALGORITHM,
    no_auth_paths=middleware_config.NO_AUTH_PATHS,
    path_matcher=path_matcher,
)

app.include_router(auth_router)
app.include_router(memory_router)
app.include_router(profile_router)
app.include_router(data_router)
app.include_router(recommendation_router)


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

init_dynamic_llm_factory(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-max",
    streaming=True,
)

agent = MathAgent(
    api_key=api_key,
    registry=registry,
    enable_dynamic_params=True,
    use_langchain_agent=True,
    enable_classifier=settings.CLASSIFIER_ENABLED,
    classifier_model=settings.CLASSIFIER_MODEL,
    classifier_config={
        "cache_max_size": settings.CLASSIFIER_CACHE_SIZE,
        "classification_timeout": settings.CLASSIFIER_TIMEOUT,
        "enable_cache": True,
        "enable_fallback": True,
    },
)

error_book_manager = ErrorBookManager()

init_default_admin(settings.JWT_SECRET_KEY)


async def _stream_agent_response(message, session_id, context_label="聊天", user_id=None):
    logger.info(f"[SSE] 开始流式响应: session={session_id}, label={context_label}, user={user_id}")
    try:
        chunk_idx = 0
        async for chunk in agent.stream(message, session_id=session_id, user_id=user_id):
            if chunk:
                if not isinstance(chunk, str):
                    chunk = str(chunk)
                chunk_idx += 1
                try:
                    yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"
                except (TypeError, ValueError) as json_error:
                    yield f"data: {json.dumps({'content': f'JSON序列化错误: {str(json_error)}', 'type': 'error'})}\n\n"

        logger.info(f"[SSE] 流式响应完成: session={session_id}, total_chunks={chunk_idx}")
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"[SSE] 流式{context_label}失败: {e}\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'content': '服务器内部错误', 'type': 'error'})}\n\n"
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"


async def stream_recognize_response(image_data, session_id):
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


async def stream_multimodal_response(message, image_data, session_id, user_id=None):
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

                async for chunk in agent.stream_multimodal(temp_file_path, message, session_id=session_id, user_id=user_id):
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
        _stream_agent_response(
            validated_message, validated_session,
            user_id=getattr(http_request.state, "user_id", None),
        ),
        media_type="text/event-stream",
    )



@app.post("/api/chat/react")
async def chat_react(request: ChatRequest, http_request: Request):
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
        _stream_agent_response(
            validated_message, validated_session, "React",
            user_id=getattr(http_request.state, "user_id", None),
        ),
        media_type="text/event-stream",
    )


@app.get("/api/agent/thought/{session_id}")
async def get_thought_history(session_id: str):
    recorder = agent.get_thought_recorder()
    processes = recorder.get_session_processes(session_id, limit=10)
    return {
        "session_id": session_id,
        "processes": [p.to_dict() for p in processes],
        "total": len(processes),
    }


@app.get("/api/agent/stats")
async def get_agent_stats():
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
            validated_message, request.image, validated_session,
            user_id=getattr(http_request.state, "user_id", None),
        ),
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

        correct_answer = validated_data.get("correct_answer", "")


        _incomplete_patterns = [
            r'^\*\*【最终答案】\*\*$',
            r'^【最终答案】$',
            r'^\*\*答案\*\*[：:]\s*$',
            r'^\*\*正确答案\*\*[：:]\s*$',
            r'^答案[：:]\s*$',
            r'^最终答案[：:]\s*$',
        ]

        _is_incomplete_answer = any(
            _re.match(pattern, correct_answer.strip(), _re.IGNORECASE)
            for pattern in _incomplete_patterns
        )

        if _is_incomplete_answer:
            logger.warning(
                f"检测到不完整的答案解析 (ID: {validated_data.get('id', 'unknown')}) - "
                f"答案内容只有标题标记，无实际解析内容。"
                f"这可能是前端extractBestAnswer函数的bug导致的。"
            )
            _warning_note = (
                "[WARN] [系统警告] 此题的答案解析可能不完整\n"
                "原因: 检测到答案只包含标题标记（如'【最终答案】'），缺少实际解题过程\n"
                "建议: 请重新添加此错题，或手动补充完整解析"
            )
            existing_notes = validated_data.get("notes", "") or ""
            validated_data["notes"] = f"{existing_notes}\n\n{_warning_note}" if existing_notes else _warning_note

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
    tools = registry.list_tools()
    return {"tools": tools, "total": len(tools)}


@app.get("/api/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    try:
        tool = registry.get_tool(tool_name)
        return tool.get_info()
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"工具未注册: '{tool_name}'")


@app.get("/api/tools/stats")
async def get_tool_stats():
    return registry.get_execution_stats()


@app.get("/api/tools/search")
async def search_tools(capability: str):
    tools = registry.search_tools(capability)
    return {"capability": capability, "tools": tools}


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "math-ai-agent-data",
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
    }


@app.get("/api/health/detailed")
async def detailed_health():
    import psutil

    checks = {
        "database": await check_database_health(),
        "cache": _check_cache_health(),
        "disk_space": _check_disk_space(),
        "memory_usage": _check_memory_usage(),
    }

    overall = "healthy" if all(
        c.get("status") == "healthy" for c in checks.values()
    ) else "degraded"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def _check_cache_health() -> dict:
    try:
        cache = get_cache_manager()
        cache_stats = cache.stats
        return {"status": "healthy", "stats": cache_stats}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


def _check_disk_space() -> dict:
    try:
        import psutil

        disk = psutil.disk_usage(".")
        percent = disk.percent
        if percent > 95:
            status = "critical"
        elif percent > 90:
            status = "warning"
        else:
            status = "healthy"
        return {
            "status": status,
            "used_percent": percent,
            "free_gb": round(disk.free / (1024**3), 2),
            "total_gb": round(disk.total / (1024**3), 2),
        }
    except ImportError:
        return {"status": "skipped", "message": "psutil 未安装"}


def _check_memory_usage() -> dict:
    try:
        import psutil

        mem = psutil.virtual_memory()
        return {
            "status": "healthy" if mem.percent < 90 else "warning",
            "used_percent": mem.percent,
            "available_mb": round(mem.available / (1024**2), 2),
            "total_gb": round(mem.total / (1024**3), 2),
        }
    except ImportError:
        return {"status": "skipped", "message": "psutil 未安装"}


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


@app.get("/chat")
@app.get("/chat/{full_path:path}")
@app.get("/error-book")
@app.get("/error-book/{full_path:path}")
async def spa_fallback(full_path: str = ""):
    return FileResponse("frontend/dist/index.html")


if __name__ == "__main__":
    if not os.path.exists("static"):
        os.makedirs("static")

    print("\n服务器启动中...")
    print("访问地址: http://localhost:8000")
    print("API文档: http://localhost:8000/docs")
    print("\n[数据库] SQLite (开发) / PostgreSQL (生产)")
    print(f"[数据库] URL: {settings.DATABASE_URL}")
    print("[缓存] Redis:", "已配置" if settings.REDIS_URL else "仅内存缓存")
    print("\n[安全] CORS已限制为:", settings.CORS_ORIGINS)
    print("[安全] JWT认证已启用")
    print("[安全] 字段级加密已启用")
    print("[安全] 审计日志已启用")
    print("[安全] 输入过滤已启用")
    print("[安全] 速率限制: {}次/分钟".format(settings.RATE_LIMIT_PER_MINUTE))
    print("\n[扩展] 插件系统: 就绪")
    print("[扩展] 数据迁移工具: python -m app.data.migrations")

    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)