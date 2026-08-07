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
from app.tasks.scheduled_tasks import get_scheduled_tasks
from agent_core import (
    AgentClassifierConfig,
    LLMConfig,
    MathAgent,
    MathAgentConfig,
)
from error_book import ErrorBookManager
from prompts.dynamic_params import init_dynamic_llm_factory
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
    )
    for router in routers:
        target_app.include_router(router)


def _build_services():
    registry = get_registry()
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
