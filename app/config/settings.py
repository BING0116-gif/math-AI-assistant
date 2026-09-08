import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    # 阈值待真实历史数据校准；环境变量用 JSON 对象配置。
    MASTERY_CONFIDENCE_CAP: dict[int, float] = Field(default_factory=lambda: {1: 0.50, 2: 0.80})
    MASTERY_CONFIDENCE_LEVELS: dict[str, tuple[int, int | None]] = Field(default_factory=lambda: {
        "insufficient": (0, 0), "low": (1, 1), "medium": (2, 2), "high": (3, None),
    })

    @field_validator("MASTERY_CONFIDENCE_CAP")
    @classmethod
    def validate_mastery_caps(cls, value):
        if any(count < 1 or not 0 <= cap <= 1 for count, cap in value.items()):
            raise ValueError("掌握度上限需为正整数证据数与 0..1 分值")
        return value

    @field_validator("MASTERY_CONFIDENCE_LEVELS")
    @classmethod
    def validate_mastery_levels(cls, value):
        if set(value) != {"insufficient", "low", "medium", "high"} or value["insufficient"] != (0, 0):
            raise ValueError("必须提供四档置信度，insufficient 为 (0, 0)")
        expected = 0
        for name in ("insufficient", "low", "medium", "high"):
            low, high = value[name]
            if low != expected or (name == "high" and high is not None) or (name != "high" and (high is None or high < low)):
                raise ValueError("置信度区间必须连续、不重叠，high 无上界")
            expected = high + 1 if high is not None else low
        return value

    # ---- T02 ReviewScheduler 间隔复习阈值：待真实复习数据校准 ----
    # 新错题首次排期的间隔（天）
    REVIEW_FIRST_INTERVAL_DAYS: int = 1
    # 复习答对后间隔的放大倍数（简单可解释策略，不引入 SM-2 等记忆曲线）
    REVIEW_CORRECT_MULTIPLIER: int = 2
    # 间隔上限（天），答对放大后不超过该值
    REVIEW_MAX_INTERVAL_DAYS: int = 30

    @field_validator("REVIEW_FIRST_INTERVAL_DAYS", "REVIEW_CORRECT_MULTIPLIER", "REVIEW_MAX_INTERVAL_DAYS")
    @classmethod
    def validate_review_scheduler_thresholds(cls, value):
        if value < 1:
            raise ValueError("间隔复习阈值必须为正整数（天/倍数）")
        return value

    APP_NAME: str = "数学AI助手"
    APP_VERSION: str = "1.6.0"
    APP_ENV: str = Field(default="development", alias="APP_ENV")
    DEBUG: bool = Field(default=False, alias="DEBUG")
    LOG_LEVEL: str = Field(default="INFO", alias="LOG_LEVEL")
    JSON_LOGS: bool = Field(default=True, alias="JSON_LOGS")
    METRICS_ENABLED: bool = Field(default=True, alias="METRICS_ENABLED")
    METRICS_BEARER_TOKEN: str = Field(default="", alias="METRICS_BEARER_TOKEN")

    # 开发/测试期临时旁路：允许 mock AI 生成的题正式发布。
    # 默认 False（与 §18 硬性规则一致，保护生产题库不被 mock 数据污染）；
    # 端到端联调或题库初始化时，可在 .env 设为 true。
    ALLOW_MOCK_PUBLISH: bool = Field(default=False, alias="ALLOW_MOCK_PUBLISH")

    DATABASE_URL: str = Field(
        default="sqlite:///./data/math_ai.db",
        alias="DATABASE_URL",
    )
    ASYNC_DATABASE_URL: str = Field(
        default="",
        alias="ASYNC_DATABASE_URL",
    )
    DB_USER: str = Field(default="mathai", alias="DB_USER")
    DB_PASSWORD: str = Field(default="changeme", alias="DB_PASSWORD")
    DB_NAME: str = Field(default="math_ai", alias="DB_NAME")
    DB_HOST: str = Field(default="localhost", alias="DB_HOST")
    DB_PORT: str = Field(default="5432", alias="DB_PORT")

    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:9000",
            "http://127.0.0.1:9000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        alias="CORS_ORIGINS",
    )
    CORS_MAX_AGE: int = Field(default=600, alias="CORS_MAX_AGE")

    JWT_SECRET_KEY: str = Field(
        default="math-ai-jwt-secret-must-be-overridden-in-production",
        alias="JWT_SECRET_KEY",
    )
    # 默认管理员凭据（内容审核后台登录用）。
    # 仅在两者都非空时，lifespan 才会创建/确认管理员角色。
    # 注意：pydantic-settings 仅把这些值读入 settings 对象、不会写回 os.environ，
    # 因此 init_default_admin 必须读 settings 而非 os.environ。
    ADMIN_USERNAME: str = Field(default="", alias="ADMIN_USERNAME")
    ADMIN_PASSWORD: str = Field(default="", alias="ADMIN_PASSWORD")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60 * 24, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=30, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS"
    )

    # ── AI 能力开关 ──
    AI_ENABLED: bool = Field(default=True, alias="AI_ENABLED")

    DASHSCOPE_API_KEY: str = Field(default="", alias="DASHSCOPE_API_KEY")

    ENCRYPTION_KEY: str = Field(default="", alias="ENCRYPTION_KEY")

    INPUT_MAX_LENGTH: int = 50000
    RATE_LIMIT_PER_MINUTE: int = 30

    AUTO_MIGRATE: bool = Field(
        default=False, alias="AUTO_MIGRATE"
    )

    # ── LLM 配置 ──
    # 主文本模型：DeepSeek（OpenAI 兼容端点）。识图链路（vision_tool / qwen-vl-*）
    # 仍使用千问 VL，只读 DASHSCOPE_API_KEY；快速分类/分析走 LLM_MATH_MODEL。
    LLM_API_KEY: str = Field(default="", alias="LLM_API_KEY")
    LLM_API_BASE: str = Field(
        default="https://api.deepseek.com/v1",
        alias="LLM_API_BASE",
    )
    LLM_MODEL: str = Field(default="deepseek-chat", alias="LLM_MODEL")
    LLM_MATH_MODEL: str = Field(default="qwen-turbo", alias="LLM_MATH_MODEL")
    LLM_TEMPERATURE: float = Field(default=0.3, alias="LLM_TEMPERATURE")
    LLM_MAX_TOKENS: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    LLM_STREAMING: bool = Field(default=True, alias="LLM_STREAMING")

    # ── 向量数据库配置 ──
    QDRANT_HOST: str = Field(default="localhost", alias="QDRANT_HOST")
    QDRANT_PORT: int = Field(default=6333, alias="QDRANT_PORT")
    VECTOR_EMBEDDING_MODEL: str = Field(default="BAAI/bge-small-zh-v1.5", alias="VECTOR_EMBEDDING_MODEL")
    VECTOR_SIZE: int = Field(default=512, alias="VECTOR_SIZE")
    QUESTION_QDRANT_COLLECTION: str = Field(default="math_questions_bge_zh_v1", alias="QUESTION_QDRANT_COLLECTION")
    OUTBOX_BATCH_SIZE: int = Field(default=50, alias="OUTBOX_BATCH_SIZE")
    OUTBOX_MAX_RETRIES: int = Field(default=8, alias="OUTBOX_MAX_RETRIES")
    OUTBOX_POLL_SECONDS: int = Field(default=5, alias="OUTBOX_POLL_SECONDS")

    # ── 记忆系统配置 ──
    MEMORY_ENABLED: bool = Field(default=True, alias="MEMORY_ENABLED")
    MEMORY_SHORT_TERM_CAPACITY: int = Field(default=20, alias="MEMORY_SHORT_TERM_CAPACITY")
    MEMORY_RETRIEVE_TOP_K: int = Field(default=7, alias="MEMORY_RETRIEVE_TOP_K")
    MEMORY_RETRIEVE_MIN_SCORE: float = Field(default=0.3, alias="MEMORY_RETRIEVE_MIN_SCORE")
    MEMORY_QDRANT_COLLECTION: str = Field(default="user_memories_bge_zh_v1", alias="MEMORY_QDRANT_COLLECTION")
    MEMORY_QDRANT_VECTOR_SIZE: int = Field(default=512, alias="MEMORY_QDRANT_VECTOR_SIZE")
    MEMORY_EMBEDDING_MODEL: str = Field(default="BAAI/bge-small-zh-v1.5", alias="MEMORY_EMBEDDING_MODEL")
    MEMORY_DECAY_INTERVAL_MINUTES: int = Field(default=1440, alias="MEMORY_DECAY_INTERVAL_MINUTES")
    MEMORY_PROFILE_CACHE_TTL: int = Field(default=86400, alias="MEMORY_PROFILE_CACHE_TTL")
    MEMORY_EVENT_IDEMPOTENCY_TTL: int = Field(default=86400, alias="MEMORY_EVENT_IDEMPOTENCY_TTL")
    MEMORY_BATCH_WRITE_SIZE: int = Field(default=10, alias="MEMORY_BATCH_WRITE_SIZE")
    MEMORY_USER_RATE_LIMIT: int = Field(default=1, alias="MEMORY_USER_RATE_LIMIT")

    # ── 出题系统适配器配置 ──
    QUESTION_SYSTEM_MODE: str = Field(default="mock", alias="QUESTION_SYSTEM_MODE")
    QUESTION_SYSTEM_API_KEY: str = Field(default="", alias="QUESTION_SYSTEM_API_KEY")
    QUESTION_SYSTEM_BASE_URL: str = Field(default="", alias="QUESTION_SYSTEM_BASE_URL")

    # ── 推荐引擎配置 ──
    RAG_ENABLED: bool = Field(default=True, alias="RAG_ENABLED")
    RAG_ENABLE_AI_EXPLANATION: bool = Field(default=True, alias="RAG_ENABLE_AI_EXPLANATION")
    RAG_ENABLE_VECTOR_SEARCH: bool = Field(default=True, alias="RAG_ENABLE_VECTOR_SEARCH")
    RAG_DEFAULT_RECOMMEND_COUNT: int = Field(default=5, alias="RAG_DEFAULT_RECOMMEND_COUNT")
    RAG_HYBRID_SEARCH_TOP_K: int = Field(default=20, alias="RAG_HYBRID_SEARCH_TOP_K")

    # ── Content Ingestion（Step 1.1-C）──
    # MinerU 独立 runtime 的可执行文件路径。生产代码只读配置，不硬编码 Demo venv 路径。
    MINERU_EXECUTABLE: str = Field(default="", alias="MINERU_EXECUTABLE")
    # MinerU 模型源（huggingface / modelscope）。传递到 subprocess env，
    # 确保 dedicated venv 命中用户级 ModelScope 模型缓存，而非触发重新下载。
    MINERU_MODEL_SOURCE: str = Field(default="modelscope", alias="MINERU_MODEL_SOURCE")
    # 正式存储根目录（仅 metadata 的相对 storage_key 落 PostgreSQL，不存绝对路径）
    CONTENT_STORAGE_ROOT: str = Field(default="./runtime/content", alias="CONTENT_STORAGE_ROOT")
    # 上传/解析安全上限（由配置而非散落的硬编码）
    CONTENT_MAX_UPLOAD_BYTES: int = Field(default=50 * 1024 * 1024, alias="CONTENT_MAX_UPLOAD_BYTES")
    CONTENT_MAX_PAGES: int = Field(default=500, alias="CONTENT_MAX_PAGES")
    # 单次解析 subprocess 超时（秒）
    CONTENT_PARSER_TIMEOUT_SECONDS: int = Field(default=600, alias="CONTENT_PARSER_TIMEOUT_SECONDS")

    # ── Content AI Pipeline（Step 1.1-E2-A0）──
    # 选择 AI 内容分析 provider：开发阶段默认 mock（不调用任何真实 AI API、
    # 不消耗 token、不要求 API Key）。真实 provider 启用后，只需在 .env 配置对应
    # API Key，后端自动检测并切换，UI / API / DB / workflow 不变。
    #   可选值：mock（默认） / deepseek（真实，OpenAI 兼容，填 DEEPSEEK_API_KEY） / qwen（占位 stub）
    CONTENT_AI_PROVIDER: str = Field(default="mock", alias="CONTENT_AI_PROVIDER")
    # 真实 Qwen provider 配置契约（仅后端读取；API Key 永不离开后端、永不传入前端）。
    # 当前 QwenContentAIProvider 仍为 stub（调用即 AI_PROVIDER_NOT_IMPLEMENTED）。
    QWEN_API_KEY: str = Field(default="", alias="QWEN_API_KEY")
    QWEN_MODEL: str = Field(default="qwen-max", alias="QWEN_MODEL")
    QWEN_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="QWEN_BASE_URL",
    )
    # 真实 DeepSeek provider 配置契约（OpenAI 兼容；API Key 只从环境变量读取）。
    # 默认 base_url 为 DeepSeek 官方兼容端点；DEEPSEEK_MODEL 可填 deepseek-chat / deepseek-reasoner。
    DEEPSEEK_API_KEY: str = Field(default="", alias="DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    DEEPSEEK_BASE_URL: str = Field(
        default="https://api.deepseek.com/v1",
        alias="DEEPSEEK_BASE_URL",
    )
    DEEPSEEK_TIMEOUT_SECONDS: int = Field(default=60, alias="DEEPSEEK_TIMEOUT_SECONDS")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
