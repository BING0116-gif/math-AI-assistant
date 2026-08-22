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
from app.api.data_api import router as data_router
from app.api.error_api import router as error_router
from app.api.events_api import router as events_router
from app.api.knowledge_api import router as knowledge_router
from app.api.memory_api import router as memory_router
from app.api.memory_dashboard import router as dashboard_router
from app.api.memory_internal_api import router as memory_internal_router
from app.api.profile_api import router as profile_router
from app.api.recommendation_api import router as recommendation_router
from app.config.settings import settings
from app.lifespan import lifespan
from app.middleware.security import SecurityValidationError
from app.middleware_setup import setup_middleware
from app.services.ai_capability import is_ai_available
from app.tasks.scheduled_tasks import get_scheduled_tasks
from error_book import ErrorBookManager
from tools import get_registry


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-6s | %(name)-30s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
    handlers=[logging.StreamHandler(sys.stdout)],
)


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
            AgentClassifierConfig,
            LLMConfig,
            MathAgent,
            MathAgentConfig,
        )
        from prompts.dynamic_params import init_dynamic_llm_factory

        init_dynamic_llm_factory(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.LLM_API_BASE,
            model=settings.LLM_MODEL,
            streaming=settings.LLM_STREAMING,
        )
        agent = MathAgent(
            MathAgentConfig(
                api_key=settings.DASHSCOPE_API_KEY,
                registry=registry,
                llm=LLMConfig(
                    model=settings.LLM_MODEL,
                    base_url=settings.LLM_API_BASE,
                ),
                classifier=AgentClassifierConfig(
                    enabled=settings.CLASSIFIER_ENABLED,
                    model=settings.CLASSIFIER_MODEL,
                    cache_max_size=settings.CLASSIFIER_CACHE_SIZE,
                    classification_timeout=settings.CLASSIFIER_TIMEOUT,
                    enable_cache=True,
                    enable_fallback=True,
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
