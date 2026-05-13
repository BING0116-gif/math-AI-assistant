from sqlalchemy import (
    Column,
    String,
    DateTime,
    Integer,
    Boolean,
    Text,
    JSON,
    Float,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timezone
import uuid


class Base(DeclarativeBase):
    pass


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