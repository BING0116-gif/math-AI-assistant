-- ============================================================
-- A03 用户技能熟练度表 (SQLite 兼容版)
-- ============================================================

CREATE TABLE IF NOT EXISTS user_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(36) NOT NULL,
    skill_code VARCHAR(50) NOT NULL,

    display_name VARCHAR(100),
    category_path VARCHAR(200),

    mastery_level REAL NOT NULL DEFAULT 0.0,

    status VARCHAR(20) NOT NULL DEFAULT 'novice',

    total_attempts INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    recent_streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,

    first_seen_at DATETIME,
    last_practiced_at DATETIME,
    mastered_at DATETIME,

    evolution_history TEXT NOT NULL DEFAULT '[]',

    created_at DATETIME DEFAULT (DATETIME('now')),
    updated_at DATETIME DEFAULT (DATETIME('now')),

    UNIQUE (user_id, skill_code)
);

CREATE INDEX IF NOT EXISTS idx_us_user_mastery
    ON user_skills (user_id, mastery_level DESC);

CREATE INDEX IF NOT EXISTS idx_us_user_status
    ON user_skills (user_id, status);

CREATE INDEX IF NOT EXISTS idx_us_skill_code
    ON user_skills (skill_code);