"""
Alembic 迁移环境配置。

支持 SQLite (开发) 和 PostgreSQL (生产) 双数据库引擎。
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# 导入所有模型，确保 Alembic 检测到表结构变更
from app.data.models import Base

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 target_metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    # 支持环境变量覆盖
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        # 转换 async URL 为 sync URL
        url = env_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # 支持环境变量覆盖数据库 URL
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        # 转换 async URL 为 sync URL
        sync_url = env_url.replace("+aiosqlite", "").replace("+asyncpg", "")
        config.set_main_option("sqlalchemy.url", sync_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()