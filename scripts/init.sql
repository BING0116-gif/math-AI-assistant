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

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'student',
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    preferences JSON DEFAULT '{}',
    last_login_at TIMESTAMP WITH TIME ZONE,
    last_login_ip VARCHAR(45),
    failed_login_count INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questions (
    id VARCHAR(20) PRIMARY KEY,
    content TEXT NOT NULL,
    question_type VARCHAR(30) NOT NULL,
    options JSON,
    answer TEXT NOT NULL,
    analysis TEXT,
    solution_steps JSON,
    category VARCHAR(50) NOT NULL,
    sub_categories VARCHAR(200),
    knowledge_points VARCHAR(500),
    difficulty INTEGER DEFAULT 3,
    complexity_score FLOAT,
    source VARCHAR(100),
    source_url VARCHAR(500),
    version INTEGER DEFAULT 1,
    tags VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE,
    estimated_time INTEGER DEFAULT 3,
    usage_count INTEGER DEFAULT 0,
    correct_rate FLOAT DEFAULT 0.0,
    avg_time_spent FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS learning_records (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    question_id VARCHAR(20) REFERENCES questions(id),
    event_type VARCHAR(30) NOT NULL,
    question_content TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    sub_categories VARCHAR(200),
    difficulty INTEGER DEFAULT 3,
    user_answer TEXT,
    correct_answer TEXT,
    is_correct BOOLEAN,
    time_spent INTEGER,
    hint_count INTEGER DEFAULT 0,
    tools_used VARCHAR(200),
    error_category VARCHAR(50),
    error_reason TEXT,
    correction_suggestion TEXT,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    title VARCHAR(200) DEFAULT '新对话',
    status VARCHAR(20) DEFAULT 'active',
    message_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    agent_strategy VARCHAR(30) DEFAULT 'react',
    tools_used VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    metadata JSON DEFAULT '{}',
    learning_record_id INTEGER REFERENCES learning_records(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exam_papers (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    title VARCHAR(200),
    config JSON NOT NULL,
    question_ids JSON NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    score FLOAT,
    max_score FLOAT DEFAULT 100,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    total_time_spent INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exam_submissions (
    id BIGSERIAL PRIMARY KEY,
    paper_id VARCHAR(36) NOT NULL REFERENCES exam_papers(id) ON DELETE CASCADE,
    question_id VARCHAR(20) NOT NULL REFERENCES questions(id),
    user_answer TEXT,
    is_correct BOOLEAN,
    score FLOAT,
    max_score FLOAT DEFAULT 10,
    time_spent INTEGER,
    hints_used INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 1,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_learning_user ON learning_records(user_id);
CREATE INDEX IF NOT EXISTS idx_learning_category ON learning_records(category);
CREATE INDEX IF NOT EXISTS idx_learning_created ON learning_records(created_at);
CREATE INDEX IF NOT EXISTS idx_learning_user_category ON learning_records(user_id, category);
CREATE INDEX IF NOT EXISTS idx_learning_user_time ON learning_records(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_learning_event_type ON learning_records(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_learning_errors ON learning_records(user_id, category) WHERE is_correct = FALSE;
CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
CREATE INDEX IF NOT EXISTS idx_questions_cat_diff ON questions(category, difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_source ON questions(source);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session_time ON chat_messages(session_id, created_at);

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO mathai;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO mathai;