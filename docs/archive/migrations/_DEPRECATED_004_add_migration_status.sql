-- ============================================================
-- 迁移状态表 (SQLite 兼容版)
-- 用途: 记录 ChromaDB -> Qdrant 迁移进度和状态
-- ============================================================

CREATE TABLE IF NOT EXISTS migration_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system VARCHAR(50) NOT NULL DEFAULT 'chromadb',
    target_system VARCHAR(50) NOT NULL DEFAULT 'qdrant',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_count INTEGER DEFAULT 0,
    migrated_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    started_at DATETIME,
    completed_at DATETIME,
    error_message TEXT,
    created_at DATETIME DEFAULT (DATETIME('now')),
    updated_at DATETIME DEFAULT (DATETIME('now'))
);

-- 迁移错误表
CREATE TABLE IF NOT EXISTS migration_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER,
    question_id VARCHAR(100),
    error_type VARCHAR(50),
    error_detail TEXT,
    created_at DATETIME DEFAULT (DATETIME('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_migration_status_status ON migration_status(status);
CREATE INDEX IF NOT EXISTS idx_migration_errors_migration_id ON migration_errors(migration_id);
CREATE INDEX IF NOT EXISTS idx_migration_errors_question_id ON migration_errors(question_id);