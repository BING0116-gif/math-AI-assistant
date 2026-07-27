-- ============================================================
-- M1 记忆系统基础表结构 (SQLite 兼容版)
-- ============================================================

-- 1. memories 表（主记忆表）
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(64) NOT NULL,
    memory_type VARCHAR(20) NOT NULL DEFAULT 'conversation',
    high_category VARCHAR(64) NOT NULL DEFAULT '',
    category VARCHAR(64) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    embedding_summary TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    difficulty INTEGER DEFAULT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    expire_at INTEGER NOT NULL,
    memory_strength REAL NOT NULL DEFAULT 0.5,
    source_id VARCHAR(64) DEFAULT NULL,
    created_at INTEGER NOT NULL,
    last_accessed INTEGER DEFAULT NULL,
    access_count INTEGER DEFAULT 0,
    deleted_at INTEGER DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_mem_user_status ON memories (user_id, status);
CREATE INDEX IF NOT EXISTS idx_mem_user_type ON memories (user_id, memory_type, status);
CREATE INDEX IF NOT EXISTS idx_mem_user_category ON memories (user_id, high_category, category, status);
CREATE INDEX IF NOT EXISTS idx_mem_expire_status ON memories (expire_at, status);
CREATE INDEX IF NOT EXISTS idx_mem_source_id ON memories (source_id, memory_type);

-- 2. memory_tags 表（记忆标签）
CREATE TABLE IF NOT EXISTS memory_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id INTEGER NOT NULL,
    tag_name VARCHAR(64) NOT NULL,
    UNIQUE (memory_id, tag_name)
);

CREATE INDEX IF NOT EXISTS idx_mtag_name ON memory_tags (tag_name);

-- 3. user_profiles 表（用户画像）
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(64) UNIQUE NOT NULL,
    summary_text TEXT NOT NULL,
    full_profile_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL,
    expire_at INTEGER DEFAULT NULL
);

-- 4. memory_access_log 表（记忆访问日志）
CREATE TABLE IF NOT EXISTS memory_access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id INTEGER NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    accessed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mal_memory_id ON memory_access_log (memory_id);
CREATE INDEX IF NOT EXISTS idx_mal_user_time ON memory_access_log (user_id, accessed_at);

-- 5. event_idempotency 表（事件幂等性保证）
CREATE TABLE IF NOT EXISTS event_idempotency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    processed_at INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'processed',
    UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS idx_ei_event_type ON event_idempotency (event_type);