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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()