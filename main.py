"""
数学AI助手 - FastAPI 应用入口。

负责：
- 创建 FastAPI 应用实例
- 配置中间件
- 注册路由
- 初始化核心组件（Agent, ErrorBookManager）
- 静态文件服务与 SPA 回退
"""

import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config.settings import settings
from app.lifespan import lifespan
from app.middleware_setup import setup_middleware
from app.middleware.security import SecurityValidationError
from app.router_registration import register_debug_routes


# 路由模块
from app.api.auth import router as auth_router
from app.api.memory_api import router as memory_router
from app.api.profile_api import router as profile_router
from app.api.data_api import router as data_router
from app.api.recommendation_api import router as recommendation_router
from app.api.chat_api import router as chat_router
from app.api.error_api import router as error_router
from app.api.agent_api import router as agent_router
from app.api.memory_internal_api import router as memory_internal_router
from app.api.events_api import router as events_router
from app.api.dev_mock_api import router as dev_mock_router
from app.api.admin_memory_api import router as admin_memory_router
from app.api.memory_dashboard import router as dashboard_router
from app.api.knowledge_api import router as knowledge_router

# 核心组件
from tools import get_registry
from agent_core import MathAgent, MathAgentConfig, AgentClassifierConfig, LLMConfig
from error_book import ErrorBookManager
from prompts.dynamic_params import init_dynamic_llm_factory

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-6s | %(name)-30s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ============================================================================
# 应用创建
# ============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

setup_middleware(app)

# 注册路由
app.include_router(auth_router)
app.include_router(memory_router)
app.include_router(profile_router)
app.include_router(data_router)
app.include_router(recommendation_router)
app.include_router(chat_router)
app.include_router(error_router)
app.include_router(agent_router)
app.include_router(memory_internal_router)
app.include_router(events_router)


register_debug_routes(app, settings.DEBUG, dev_mock_router)
app.include_router(admin_memory_router)
app.include_router(dashboard_router)
app.include_router(knowledge_router)

# ============================================================================
# 核心组件初始化
# ============================================================================

api_key = settings.DASHSCOPE_API_KEY
registry = get_registry()

init_dynamic_llm_factory(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model=settings.LLM_MODEL,
    streaming=True,
)

agent = MathAgent(
    MathAgentConfig(
        api_key=api_key,
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

error_book_manager = ErrorBookManager()  # 使用数据库存储，无需 data_file 参数

# 启动记忆系统定时任务
try:
    from app.tasks.scheduled_tasks import get_scheduled_tasks
    scheduled_tasks = get_scheduled_tasks()
    scheduled_tasks.start_scheduler()
    logger.info("[记忆系统] 定时任务已启动")
except Exception as e:
    logger.warning(f"[记忆系统] 定时任务启动失败（非关键错误）: {e}")

# ============================================================================
# 异常处理
# ============================================================================

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

# ============================================================================
# 静态文件与 SPA 回退
# ============================================================================

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
@app.get("/knowledge")
async def spa_fallback(full_path: str = ""):
    return FileResponse("frontend/dist/index.html")

# ============================================================================
# 启动入口
# ============================================================================

if __name__ == "__main__":
    if not os.path.exists("static"):
        os.makedirs("static")

    print("\n服务器启动中...")
    print("访问地址: http://localhost:8000")
    print("API文档: http://localhost:8000/docs")
    print("\n[数据库] SQLite (开发) / PostgreSQL (生产)")
    print(f"[数据库] URL: {settings.DATABASE_URL}")
    print("[缓存] Redis:", "已配置" if settings.REDIS_URL else "仅内存缓存")
    print(f"\n[安全] CORS已限制为: {settings.CORS_ORIGINS}")
    print("[安全] JWT认证已启用")
    print("[安全] 字段级加密已启用")
    print("[安全] 审计日志已启用")
    print("[安全] 输入过滤已启用")
    print("[安全] 速率限制: {}次/分钟".format(settings.RATE_LIMIT_PER_MINUTE))
    print("\n[扩展] 插件系统: 就绪")
    print("[扩展] 数据迁移工具: python -m app.data.migrations")
    print("\n[记忆系统] 记忆存储层: 就绪")
    print("[记忆系统] 记忆检索引擎: 就绪")
    print("[记忆系统] 用户画像系统: 就绪")
    print("[记忆系统] 定时任务: 已启动")
    print("[记忆系统] Mock测试接口: 已启用")
    print(f"[记忆系统] 出题系统适配模式: {settings.QUESTION_SYSTEM_MODE}")

    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
