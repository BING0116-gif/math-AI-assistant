"""Application assembly for the Math AI Assistant.

This module is the single place where the FastAPI application, routers and
process-level services are assembled.  ``main.py`` remains as a compatibility
shim for existing commands and tests.
"""

import logging
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.admin_memory_api import router as admin_memory_router
from app.api.agent_api import router as agent_router
from app.api.auth import router as auth_router
from app.api.chat_api import router as chat_router
from app.api.content_import_api import router as content_import_router
from app.api.content_ai_api import router as content_ai_router
from app.api.paper_api import router as paper_router
from app.api.paper_student_api import router as paper_student_router
from app.api.practice_api import router as practice_router
from app.api.assessment_api import router as assessment_router
from app.api.exam_api import router as exam_router
from app.api.data_api import router as data_router
from app.api.error_api import router as error_router
from app.api.events_api import router as events_router
from app.api.knowledge_api import router as knowledge_router
from app.api.memory_api import router as memory_router
from app.api.memory_dashboard import router as dashboard_router
from app.api.memory_internal_api import router as memory_internal_router
from app.api.profile_api import router as profile_router
from app.api.recommendation_api import router as recommendation_router
from app.api.learning_hub_api import router as learning_hub_router
from app.api.legacy_import_api import router as legacy_import_router
from app.api.readiness_api import router as readiness_router
from app.config.settings import settings
from app.lifespan import lifespan
from app.middleware.security import SecurityValidationError
from app.middleware_setup import setup_middleware
from app.services.ai_capability import is_ai_available
from app.tasks.scheduled_tasks import get_scheduled_tasks
from error_book import ErrorBookManager
from tools import get_registry
from app.observability import configure_json_logging, metrics_response


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-6s | %(name)-30s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    # Do not replace handlers installed by the host process (pytest caplog,
    # uvicorn, observability agents). Replacing them makes logs disappear and
    # breaks process-wide instrumentation merely by importing the app.
    force=False,
    handlers=[logging.StreamHandler(sys.stdout)],
)
if settings.JSON_LOGS:
    configure_json_logging(settings.LOG_LEVEL)


def _register_routers(target_app: FastAPI) -> None:
    routers = (
        auth_router,
        memory_router,
        profile_router,
        data_router,
        recommendation_router,
        chat_router,
        error_router,
        agent_router,
        memory_internal_router,
        events_router,
        admin_memory_router,
        dashboard_router,
        knowledge_router,
        content_import_router,
        content_ai_router,
        paper_router,
        paper_student_router,
        practice_router,
        assessment_router,
        exam_router,
        learning_hub_router,
        legacy_import_router,
        readiness_router,
    )
    for router in routers:
        target_app.include_router(router)


def _build_services():
    """构建所有全局服务实例。

    AI 相关服务（MathAgent、动态参数工厂）仅在 AI 可用时构建。
    ErrorBookManager 和工具注册表始终构建，不依赖 AI。
    """
    registry = get_registry()

    agent = None  # type: ignore[assignment]
    if is_ai_available():
        # 延迟导入 AI 相关模块，避免 AI 不可用时 import 失败
        from agent_core import (
            LLMConfig,
            MathAgent,
            MathAgentConfig,
        )
        from prompts.dynamic_params import init_dynamic_llm_factory

        # 文本 LLM 密钥：优先 LLM_API_KEY，兜底 DASHSCOPE_API_KEY。
        # 视觉链路（vision_tool / qwen-vl-plus）仍只读 DASHSCOPE_API_KEY，互不影响。
        _agent_api_key = settings.LLM_API_KEY or settings.DASHSCOPE_API_KEY
        _llm_api_base = settings.LLM_API_BASE or "https://api.deepseek.com/v1"
        _llm_model = settings.LLM_MODEL or "deepseek-chat"
        # 若配置把主文本链路指向 DeepSeek 端点却遗留千问默认模型名，
        # 自动对齐到 DeepSeek 文本模型，避免向 DeepSeek 发送 qwen-* 导致 404。
        if "deepseek" in _llm_api_base.lower() and _llm_model.startswith("qwen"):
            _llm_model = "deepseek-chat"
        init_dynamic_llm_factory(
            api_key=_agent_api_key,
            base_url=_llm_api_base,
            model=_llm_model,
            streaming=settings.LLM_STREAMING,
        )
        agent = MathAgent(
            MathAgentConfig(
                api_key=_agent_api_key,
                registry=registry,
                llm=LLMConfig(
                    model=_llm_model,
                    base_url=_llm_api_base,
                ),
            )
        )
        logger.info("MathAgent 已初始化（AI Enabled）")
    else:
        cap = __import__("app.services.ai_capability", fromlist=["get_ai_capability"]).get_ai_capability()
        logger.info("AI 服务未初始化，原因: %s（AI 不可用模式）", cap.reason)

    return registry, agent, ErrorBookManager()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)
setup_middleware(app)
_register_routers(app)

registry, agent, error_book_manager = _build_services()

scheduled_tasks = get_scheduled_tasks()


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    if not settings.METRICS_ENABLED:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    expected = settings.METRICS_BEARER_TOKEN
    if expected and request.headers.get("authorization") != f"Bearer {expected}":
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return metrics_response()


@app.get("/", include_in_schema=False)
async def root() -> JSONResponse:
    """友好的根页面：告诉用户后端正常运行、该去哪里。

    纯 API 后端没有 UI，访问 `/` 之前会返回 404 Not Found。
    这里显式提供一个 JSON 概览，避免误判为服务挂了。
    """
    return JSONResponse(
        status_code=200,
        content={
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "docs": "/docs" if settings.DEBUG else "(disabled in production)",
            "openapi": "/openapi.json",
            "hint": "API endpoints are mounted under /api/* — see /openapi.json for the full list.",
        },
    )


@app.exception_handler(SecurityValidationError)
async def security_validation_handler(request: Request, exc: SecurityValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "threat_type": exc.threat_type},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled application error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})
