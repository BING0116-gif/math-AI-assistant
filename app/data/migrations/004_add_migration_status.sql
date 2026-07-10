-- 迁移状态表
-- 创建时间: 2026-07-10
-- 用途: 记录 ChromaDB -> Qdrant 迁移进度和状态

CREATE TABLE IF NOT EXISTS migration_status (
    id SERIAL PRIMARY KEY,
    source_system VARCHAR(50) NOT NULL DEFAULT 'chromadb',
    target_system VARCHAR(50) NOT NULL DEFAULT 'qdrant',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_count INTEGER DEFAULT 0,
    migrated_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 迁移错误表
CREATE TABLE IF NOT EXISTS migration_errors (
    id SERIAL PRIMARY KEY,
    migration_id INTEGER REFERENCES migration_status(id) ON DELETE CASCADE,
    question_id VARCHAR(100),
    error_type VARCHAR(50),
    error_detail TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_migration_status_status ON migration_status(status);
CREATE INDEX IF NOT EXISTS idx_migration_errors_migration_id ON migration_errors(migration_id);
CREATE INDEX IF NOT EXISTS idx_migration_errors_question_id ON migration_errors(question_id);
