-- PostgreSQL 初始化脚本（仅用于 Docker 首次启动）
-- 数据库用户和扩展由 Alembic 迁移管理，此处仅创建基本角色和扩展

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_user WHERE usename = 'mathai'
    ) THEN
        CREATE ROLE mathai WITH LOGIN PASSWORD 'changeme';
    END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE math_ai TO mathai;

-- 注意：表结构由 Alembic 迁移管理
-- 应用启动时自动执行 `alembic upgrade head` 创建/更新所有表