-- ============================================================
-- A03 用户技能熟练度表
-- 必须在启动任何 T1-T8 开发前执行
-- ============================================================

CREATE TABLE IF NOT EXISTS user_skills (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    skill_code VARCHAR(50) NOT NULL,

    display_name VARCHAR(100),
    category_path VARCHAR(200),

    mastery_level FLOAT NOT NULL DEFAULT 0.0
        CHECK (mastery_level >= 0.0 AND mastery_level <= 1.0),

    status VARCHAR(20) NOT NULL DEFAULT 'novice'
        CHECK (status IN ('novice', 'learning', 'proficient', 'mastered')),

    total_attempts INT NOT NULL DEFAULT 0,
    correct_count INT NOT NULL DEFAULT 0,
    recent_streak INT NOT NULL DEFAULT 0,
    best_streak INT NOT NULL DEFAULT 0,

    first_seen_at TIMESTAMPTZ,
    last_practiced_at TIMESTAMPTZ,
    mastered_at TIMESTAMPTZ,

    evolution_history JSONB NOT NULL DEFAULT '[]',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (user_id, skill_code)
);

CREATE INDEX IF NOT EXISTS idx_us_user_mastery
    ON user_skills (user_id, mastery_level DESC);

CREATE INDEX IF NOT EXISTS idx_us_user_status
    ON user_skills (user_id, status);

CREATE INDEX IF NOT EXISTS idx_us_skill_code
    ON user_skills (skill_code);