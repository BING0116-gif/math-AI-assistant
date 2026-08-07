import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    APP_NAME: str = "数学AI助手"
    APP_VERSION: str = "1.6.0"
    DEBUG: bool = Field(default=False, alias="DEBUG")

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
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60 * 24, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=30, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS"
    )

    DASHSCOPE_API_KEY: str = Field(default="", alias="DASHSCOPE_API_KEY")

    ENCRYPTION_KEY: str = Field(default="", alias="ENCRYPTION_KEY")

    INPUT_MAX_LENGTH: int = 50000
    RATE_LIMIT_PER_MINUTE: int = 30

    AUTO_MIGRATE: bool = Field(
        default=False, alias="AUTO_MIGRATE"
    )

    CLASSIFIER_ENABLED: bool = Field(
        default=True,
        alias="CLASSIFIER_ENABLED",
    )
    CLASSIFIER_MODEL: str = Field(
        default="qwen-turbo",
        alias="CLASSIFIER_MODEL",
    )
    CLASSIFIER_CACHE_SIZE: int = Field(
        default=2000,
        alias="CLASSIFIER_CACHE_SIZE",
    )
    CLASSIFIER_TIMEOUT: float = Field(
        default=5.0,
        alias="CLASSIFIER_TIMEOUT",
    )

    # ── LLM 配置 ──
    LLM_API_KEY: str = Field(default="", alias="LLM_API_KEY")
    LLM_API_BASE: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="LLM_API_BASE",
    )
    LLM_MODEL: str = Field(default="qwen-max", alias="LLM_MODEL")
    LLM_MATH_MODEL: str = Field(default="qwen-turbo", alias="LLM_MATH_MODEL")
    LLM_TEMPERATURE: float = Field(default=0.3, alias="LLM_TEMPERATURE")
    LLM_MAX_TOKENS: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    LLM_STREAMING: bool = Field(default=True, alias="LLM_STREAMING")

    # ── 向量数据库配置 ──
    VECTOR_EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2", alias="VECTOR_EMBEDDING_MODEL")

    # ── 记忆系统配置 ──
    MEMORY_ENABLED: bool = Field(default=True, alias="MEMORY_ENABLED")
    MEMORY_SHORT_TERM_CAPACITY: int = Field(default=20, alias="MEMORY_SHORT_TERM_CAPACITY")
    MEMORY_RETRIEVE_TOP_K: int = Field(default=7, alias="MEMORY_RETRIEVE_TOP_K")
    MEMORY_RETRIEVE_MIN_SCORE: float = Field(default=0.3, alias="MEMORY_RETRIEVE_MIN_SCORE")
    MEMORY_QDRANT_COLLECTION: str = Field(default="user_memories", alias="MEMORY_QDRANT_COLLECTION")
    MEMORY_QDRANT_VECTOR_SIZE: int = Field(default=384, alias="MEMORY_QDRANT_VECTOR_SIZE")
    MEMORY_EMBEDDING_MODEL: str = Field(default="bge-small-zh-v1.5", alias="MEMORY_EMBEDDING_MODEL")
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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
