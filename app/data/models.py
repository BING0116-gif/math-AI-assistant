from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
    Float,
    Integer,
    ForeignKey,
    JSON,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timezone
import uuid


class Base(DeclarativeBase):
    pass


class Course(Base):
    """A subject-level course with one currently published knowledge version."""
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(80), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    subject = Column(String(80), nullable=False)
    default_version_id = Column(String(36), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    versions = relationship("KnowledgeGraphVersion", back_populates="course", cascade="all, delete-orphan")


class KnowledgeGraphVersion(Base):
    __tablename__ = "knowledge_graph_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(40), nullable=False)
    name = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    based_on_version_id = Column(String(36), nullable=True)
    created_by = Column(String(36), nullable=True)
    published_by = Column(String(36), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    course = relationship("Course", back_populates="versions")
    chapters = relationship("Chapter", back_populates="version", cascade="all, delete-orphan")
    points = relationship("KnowledgePoint", back_populates="version", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("course_id", "version", name="uq_course_graph_version"),)


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("knowledge_graph_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=True, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    sort_order = Column(Integer, nullable=False, default=0)
    level = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    version = relationship("KnowledgeGraphVersion", back_populates="chapters")
    parent = relationship("Chapter", remote_side=[id], backref="children")
    points = relationship("KnowledgePoint", back_populates="chapter")
    __table_args__ = (UniqueConstraint("version_id", "code", name="uq_chapter_version_code"),)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("knowledge_graph_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    aliases = Column(JSON, nullable=False, default=list)
    learning_objectives = Column(JSON, nullable=False, default=list)
    common_errors = Column(JSON, nullable=False, default=list)
    key_concepts = Column(JSON, nullable=False, default=list)
    key_formulas = Column(JSON, nullable=False, default=list)
    exam_focuses = Column(JSON, nullable=False, default=list)
    difficulty = Column(Integer, nullable=False, default=1)
    importance = Column(Float, nullable=False, default=0.5)
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    version = relationship("KnowledgeGraphVersion", back_populates="points")
    chapter = relationship("Chapter", back_populates="points")
    resources = relationship("KnowledgePointResource", back_populates="knowledge_point", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("version_id", "code", name="uq_point_version_code"),
        Index("idx_point_version_chapter_order", "version_id", "chapter_id", "sort_order"),
    )


class KnowledgePointResource(Base):
    """A versioned learning asset attached to one knowledge point.

    The resource table keeps lessons, formulas, worked examples and exercises
    independent so later authoring/import and question-bank phases need not
    change the knowledge graph schema.
    """
    __tablename__ = "knowledge_point_resources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_point_id = Column(String(36), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String(30), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False, default="")
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="published")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    knowledge_point = relationship("KnowledgePoint", back_populates="resources")
    __table_args__ = (
        UniqueConstraint("knowledge_point_id", "resource_type", "title", name="uq_point_resource_type_title"),
        Index("idx_point_resource_order", "knowledge_point_id", "resource_type", "sort_order"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="student")
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    preferences = Column(JSON, default=dict)
    last_login_at = Column(DateTime(timezone=True))
    last_login_ip = Column(String(45))
    failed_login_count = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sessions = relationship(
        "ChatSession", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    learning_records = relationship(
        "LearningRecord", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    exam_papers = relationship(
        "ExamPaper", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    user_skills = relationship(
        "UserSkill", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    error_items = relationship(
        "ErrorItem", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )


class LearningRecord(Base):
    __tablename__ = "learning_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    question_id = Column(String(20), ForeignKey("questions.id"), nullable=True, index=True)

    user = relationship("User", back_populates="learning_records")
    question = relationship("Question", back_populates="learning_records")

    event_type = Column(String(30), nullable=False, index=True)
    question_content = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, index=True)
    sub_categories = Column(String(200))
    difficulty = Column(Integer, default=3)
    user_answer = Column(Text)
    correct_answer = Column(Text)
    is_correct = Column(Boolean, default=None)
    time_spent = Column(Integer)
    hint_count = Column(Integer, default=0)
    tools_used = Column(String(200))
    error_category = Column(String(50))
    error_reason = Column(Text)
    correction_suggestion = Column(Text)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("idx_learning_user_category", "user_id", "category"),
        Index("idx_learning_user_time", "user_id", "created_at"),
        Index("idx_learning_event_type", "event_type", "created_at"),
        Index("idx_learning_errors", "user_id", "category", postgresql_where="is_correct = FALSE"),
    )


class UserSkill(Base):
    """用户技能熟练度表（A03 Skill机制）"""
    __tablename__ = "user_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    skill_code = Column(String(50), nullable=False)
    display_name = Column(String(100))
    category_path = Column(String(200))

    mastery_level = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="novice")

    total_attempts = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    recent_streak = Column(Integer, nullable=False, default=0)
    best_streak = Column(Integer, nullable=False, default=0)

    first_seen_at = Column(DateTime(timezone=True))
    last_practiced_at = Column(DateTime(timezone=True))
    mastered_at = Column(DateTime(timezone=True))

    evolution_history = Column(JSON, default=list)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="user_skills")

    __table_args__ = (
        Index("idx_us_user_mastery", "user_id", "mastery_level"),
        Index("idx_us_user_status", "user_id", "status"),
        Index("idx_us_skill_code", "skill_code"),
        UniqueConstraint("user_id", "skill_code", name="uq_user_skill"),
    )


class Question(Base):
    __tablename__ = "questions"

    id = Column(String(20), primary_key=True)
    content = Column(Text, nullable=False)
    question_type = Column(String(30), nullable=False, index=True)
    options = Column(JSON)
    answer = Column(Text, nullable=False)
    analysis = Column(Text)
    solution_steps = Column(JSON)
    category = Column(String(50), nullable=False, index=True)
    sub_categories = Column(String(200))
    knowledge_points = Column(String(500))
    difficulty = Column(Integer, default=3, index=True)
    complexity_score = Column(Float)
    source = Column(String(100))
    source_url = Column(String(500))
    version = Column(Integer, default=1)
    tags = Column(String(500))
    is_active = Column(Boolean, default=True, index=True)
    estimated_time = Column(Integer, default=3)
    usage_count = Column(Integer, default=0)
    correct_rate = Column(Float, default=0.0)
    avg_time_spent = Column(Float, default=0.0)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    learning_records = relationship("LearningRecord", back_populates="question", lazy="dynamic")

    __table_args__ = (
        Index("idx_question_category_difficulty", "category", "difficulty"),
        Index("idx_question_source", "source"),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )

    user = relationship("User", back_populates="sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        order_by="ChatMessage.created_at",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    title = Column(String(200), default="新对话")
    status = Column(String(20), default="active")
    message_count = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    agent_strategy = Column(String(30), default="react")
    tools_used = Column(String(200))
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True
    )

    session = relationship("ChatSession", back_populates="messages")

    role = Column(String(20), nullable=False, index=True)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    metadata_ = Column("metadata", JSON, default=dict)
    learning_record_id = Column(
        Integer, ForeignKey("learning_records.id"), nullable=True
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("idx_message_session_time", "session_id", "created_at"),
    )


class ExamPaper(Base):
    __tablename__ = "exam_papers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )

    user = relationship("User", back_populates="exam_papers")
    submissions = relationship(
        "ExamSubmission", back_populates="paper", lazy="dynamic", cascade="all, delete-orphan"
    )

    title = Column(String(200))
    config = Column(JSON, nullable=False)
    question_ids = Column(JSON, nullable=False)
    status = Column(String(20), default="pending")
    score = Column(Float)
    max_score = Column(Float, default=100)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    total_time_spent = Column(Integer)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class ExamSubmission(Base):
    __tablename__ = "exam_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(
        String(36), ForeignKey("exam_papers.id"), nullable=False
    )
    question_id = Column(
        String(20), ForeignKey("questions.id"), nullable=False
    )

    paper = relationship("ExamPaper", back_populates="submissions")
    question = relationship("Question")

    user_answer = Column(Text)
    is_correct = Column(Boolean)
    score = Column(Float)
    max_score = Column(Float, default=10)
    time_spent = Column(Integer)
    hints_used = Column(Integer, default=0)
    attempts = Column(Integer, default=1)
    submitted_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class RefreshToken(Base):
    """刷新令牌表 - 替代内存字典存储"""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_type = Column(String(20), default="refresh")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User")


class ErrorItem(Base):
    """错题本表 - 替代 JSON 文件存储"""
    __tablename__ = "error_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    item_id = Column(String(64), nullable=False, index=True, comment="原始错题 ID")
    question = Column(Text, nullable=False)
    question_type = Column(String(20), default="text")
    image_path = Column(String(500))
    error_reason = Column(Text, default="")
    categories = Column(JSON, default=list)
    original_answer = Column(Text, default="")
    correct_answer = Column(Text, default="")
    notes = Column(Text, default="")
    added_at = Column(String(30), default="")
    mastery_level = Column(Integer, default=3)
    is_mastered = Column(Boolean, default=False)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="error_items")

    __table_args__ = (
        Index("idx_error_items_user", "user_id", "is_mastered"),
        Index("idx_error_items_user_item", "user_id", "item_id", unique=True),
    )


class MigrationStatus(Base):
    """迁移状态表"""
    __tablename__ = "migration_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_system = Column(String(50), default="chromadb")
    target_system = Column(String(50), default="qdrant")
    status = Column(String(20), default="pending")
    total_count = Column(Integer, default=0)
    migrated_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MigrationError(Base):
    """迁移错误表"""
    __tablename__ = "migration_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    migration_id = Column(Integer, ForeignKey("migration_status.id"))
    question_id = Column(String(100))
    error_type = Column(String(50))
    error_detail = Column(Text)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Memory(Base):
    """记忆主表"""
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    memory_type = Column(String(20), default="conversation")
    high_category = Column(String(64), default="")
    category = Column(String(64), default="")
    content = Column(Text, nullable=False)
    embedding_summary = Column(Text, nullable=False)
    importance = Column(Float, default=0.5)
    difficulty = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")
    expire_at = Column(Integer, nullable=False)
    memory_strength = Column(Float, default=0.5)
    source_id = Column(String(64), nullable=True)
    created_at = Column(Integer, nullable=False)
    last_accessed = Column(Integer, nullable=True)
    access_count = Column(Integer, default=0)
    deleted_at = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_mem_user_status", "user_id", "status"),
        Index("idx_mem_user_type", "user_id", "memory_type", "status"),
        Index("idx_mem_user_category", "user_id", "high_category", "category", "status"),
        Index("idx_mem_expire_status", "expire_at", "status"),
        Index("idx_mem_source_id", "source_id", "memory_type"),
    )


class MemoryTag(Base):
    """记忆标签表"""
    __tablename__ = "memory_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(Integer, ForeignKey("memories.id"), nullable=False)
    tag_name = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("memory_id", "tag_name", name="uq_memory_tag"),
        Index("idx_mtag_name", "tag_name"),
    )


class UserProfile(Base):
    """用户画像表"""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    summary_text = Column(Text, nullable=False)
    full_profile_json = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    updated_at = Column(Integer, nullable=False)
    expire_at = Column(Integer, nullable=True)


class MemoryAccessLog(Base):
    """记忆访问日志表"""
    __tablename__ = "memory_access_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(Integer, ForeignKey("memories.id"), nullable=False)
    user_id = Column(String(64), nullable=False)
    session_id = Column(String(128), nullable=False)
    accessed_at = Column(Integer, nullable=False)

    __table_args__ = (
        Index("idx_mal_memory_id", "memory_id"),
        Index("idx_mal_user_time", "user_id", "accessed_at"),
    )


class EventIdempotency(Base):
    """事件幂等性表"""
    __tablename__ = "event_idempotency"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), nullable=False, unique=True)
    event_type = Column(String(64), nullable=False)
    processed_at = Column(Integer, nullable=False)
    status = Column(String(20), default="processed")

    __table_args__ = (
        Index("idx_ei_event_type", "event_type"),
    )
