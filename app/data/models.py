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
    # 前置知识点 code 列表（稳定 code，非 id），用于表达学习依赖关系
    prerequisites = Column(JSON, nullable=False, default=list)
    # 关联知识点 code 列表（跨章节关联，非前置依赖）
    related = Column(JSON, nullable=False, default=list)
    difficulty = Column(Integer, nullable=False, default=1)
    importance = Column(Float, nullable=False, default=0.5)
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    version = relationship("KnowledgeGraphVersion", back_populates="points")
    chapter = relationship("Chapter", back_populates="points")
    resources = relationship("KnowledgePointResource", back_populates="knowledge_point", cascade="all, delete-orphan")
    questions = relationship("QuestionKnowledgePoint", back_populates="knowledge_point", cascade="all, delete-orphan")
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
    # 旧字段：逗号/JSON 字符串形式的知识点展示名，仅保持只读兼容；正式事实来源见 question_knowledge_points 关联表
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
    # 所属课程与课程版本（稳定 ID）；范围外/未归属题允许为空
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=True, index=True)
    version_id = Column(String(36), ForeignKey("knowledge_graph_versions.id", ondelete="RESTRICT"), nullable=True, index=True)
    # 审核状态：draft / reviewed / published / retired；只有 published 可进入正式练习选池
    review_status = Column(String(20), nullable=False, default="draft", index=True)
    # AI 生成标记：AI 生成题默认 draft，不得自动发布
    is_ai_generated = Column(Boolean, nullable=False, default=False)
    # 常见错误（结构化）：{"version": 1, "items": [{"type","description","suggestion"}]}
    common_mistakes = Column(JSON)
    # 标准答案规范（按题型分结构，供 Step 1.4 判题使用）：{"version": 1, "kind": "choice|judge|numeric|expression", ...}
    answer_spec = Column(JSON)
    # 判题/组卷能力（P0-7，发布时按题型派生）：组卷只消费 exam_eligible + auto_grading_eligible 的题
    grading_mode = Column(String(20), nullable=False, default="manual")  # deterministic / llm_assisted / manual
    practice_eligible = Column(Boolean, nullable=False, default=False)
    exam_eligible = Column(Boolean, nullable=False, default=False)
    auto_grading_eligible = Column(Boolean, nullable=False, default=False, index=True)
    # 来源候选（Content Import staging）：完整 provenance 经 candidate → ImportBatch → SourceDocument 回查。
    # UNIQUE：同一 candidate 只能落一条正式 Question（幂等，禁止重复 draft）。
    source_candidate_id = Column(
        String(36),
        ForeignKey("content_import_candidates.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
        index=True,
    )
    # AI enrichment provider that produced the structured enrichment for this
    # question (via the source candidate's analysis run). 'mock' results are
    # blocked from formal publishing by the review service (MOCK_AI_RESULT_NOT_PUBLISHABLE).
    ai_provider = Column(String(30), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    learning_records = relationship("LearningRecord", back_populates="question", lazy="dynamic")
    knowledge_point_links = relationship("QuestionKnowledgePoint", back_populates="question", cascade="all, delete-orphan")
    source_candidate = relationship("ContentImportCandidate", back_populates="questions")

    __table_args__ = (
        Index("idx_question_category_difficulty", "category", "difficulty"),
        Index("idx_question_source", "source"),
        Index("idx_question_review_status", "review_status"),
    )


class QuestionKnowledgePoint(Base):
    """规范化 Question ↔ KnowledgePoint 多对多关联（正式事实来源）。"""
    __tablename__ = "question_knowledge_points"

    question_id = Column(String(20), ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    knowledge_point_id = Column(String(36), ForeignKey("knowledge_points.id", ondelete="CASCADE"), primary_key=True)
    # 是否为主知识点（用于练习/技能归属的首要目标）
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    question = relationship("Question", back_populates="knowledge_point_links")
    knowledge_point = relationship("KnowledgePoint", back_populates="questions")

    __table_args__ = (
        Index("idx_qkp_knowledge_point", "knowledge_point_id"),
    )


class SourceDocument(Base):
    """Content Ingestion 来源文档事实。

    只保存文档 metadata（hash / 存储 key），不把 PDF binary 塞进 DB；
    存储 key 为相对/逻辑路径，禁止保存 Windows 绝对路径。
    删除策略：RESTRICT（已关联 ImportBatch 后禁止物理删除，避免 provenance 断链）。
    """
    __tablename__ = "source_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_filename = Column(String(255), nullable=False)
    storage_key = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    mime_type = Column(String(120), nullable=False, default="application/pdf")
    size_bytes = Column(Integer, nullable=False, default=0)
    created_by = Column(String(36), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    batches = relationship("ImportBatch", back_populates="source_document")

    __table_args__ = (
        Index("idx_source_doc_created_by", "created_by", "created_at"),
    )


class ImportBatch(Base):
    """某次对 SourceDocument 的解析运行。

    状态机：pending / parsing / parsed / failed / completed。
    幂等：同一 admin + idempotency_key 不得重复创建批次。
    """
    __tablename__ = "import_batches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_document_id = Column(
        String(36),
        ForeignKey("source_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String(20), nullable=False, default="pending", index=True)
    parser_name = Column(String(50), nullable=False)
    parser_version = Column(String(50), default="")
    created_by = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    stats = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(100), nullable=True)

    source_document = relationship("SourceDocument", back_populates="batches")
    candidates = relationship(
        "ContentImportCandidate",
        back_populates="import_batch",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("created_by", "idempotency_key", name="uq_import_batch_idem"),
        Index("idx_import_batch_source", "source_document_id", "status"),
    )


class ContentImportCandidate(Base):
    """内容导入 staging / workflow 记录。

    不是第二套正式 Question domain；学生端、练习、推荐不得直接读取。
    原始内容（raw_parsed_content）、原答案（original_answer / original_solution）
    属于 provenance，一旦写入不随 candidate 编辑而覆盖。
    """
    __tablename__ = "content_import_candidates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_batch_id = Column(
        String(36),
        ForeignKey("import_batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    candidate_index = Column(Integer, nullable=False, default=0)
    source_page_start = Column(Integer, nullable=True)
    source_page_end = Column(Integer, nullable=True)
    source_question_number = Column(String(50), nullable=True)
    raw_parsed_content = Column(Text, nullable=True)
    stem = Column(Text, nullable=True)
    options = Column(JSON, nullable=True)
    original_answer = Column(Text, nullable=True)
    original_solution = Column(Text, nullable=True)
    detected_question_type = Column(String(30), nullable=True)
    supported = Column(Boolean, nullable=False, default=False)
    warnings = Column(JSON, nullable=False, default=list)
    suggested_knowledge_point_codes = Column(JSON, nullable=False, default=list)
    # 状态机：parsed / edited / imported / rejected
    status = Column(String(20), nullable=False, default="parsed", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    import_batch = relationship("ImportBatch", back_populates="candidates")
    questions = relationship("Question", back_populates="source_candidate")
    # AI 分析运行历史（1 candidate → N runs）。禁止删除 candidate 后丢失 AI 审计记录。
    ai_analysis_runs = relationship(
        "ContentAIAnalysisRun",
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="ContentAIAnalysisRun.attempt_no",
    )

    __table_args__ = (
        Index("idx_candidate_batch_index", "import_batch_id", "candidate_index"),
        Index("idx_candidate_status", "status"),
    )


class ContentAIAnalysisRun(Base):
    """某 candidate 的一次 AI 分析运行事实（Step 1.1-E2-A0）。

    不是 Question domain；表示 AI 是否已把某 candidate 分析好。状态机：
        pending → analyzing → validating → verifying → pass / doubtful / failed
    每次重新分析创建一条新 run（parent_run_id 指向先前 run），历史全部保留，
    禁止第二次分析直接覆盖第一次 JSON。

    字段语义见 Step 1.1-E2-A0 §11：
    - provider / model / prompt_version：产生本次结果的 AI provider 事实
    - analysis_json / verifier_json：结构化分析与验证结果
    - gate / gate_reasons：最终 PASS / DOUBTFUL / FAILED 与原因
    - attempt_no / parent_run_id：重新分析序号与血缘
    - human_disposition / human_note：人工处置（approved/doubtful/reject/reanalyze）
    - error_code / error_message：失败原因
    - started_at / completed_at：运行起止时间

    删除策略：candidate_id RESTRICT（删 candidate 前必须清理 run，避免
    provenance 断链）；parent_run_id 自引用 RESTRICT（run 一旦成为父节点不可删）。
    """

    __tablename__ = "content_ai_analysis_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(
        String(36),
        ForeignKey("content_import_candidates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # provider 事实：'mock' 必须醒目标记，且由 review service 阻止基于此结果的正式发布。
    provider = Column(String(30), nullable=False, default="mock", index=True)
    model = Column(String(80), nullable=True)
    prompt_version = Column(String(40), nullable=True)

    # 状态机：pending / analyzing / validating / verifying / pass / doubtful / failed
    status = Column(String(20), nullable=False, default="pending", index=True)
    # 最终 gate（仅在 terminal 状态稳定）：PASS / DOUBTFUL / FAILED / null
    gate = Column(String(20), nullable=True, index=True)

    analysis_json = Column(JSON, nullable=True)
    verifier_json = Column(JSON, nullable=True)
    gate_reasons = Column(JSON, nullable=False, default=list)

    attempt_no = Column(Integer, nullable=False, default=1)
    parent_run_id = Column(
        String(36),
        ForeignKey("content_ai_analysis_runs.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # 人工处置：approved / doubtful / reject / reanalyze / null
    human_disposition = Column(String(20), nullable=True, index=True)
    human_note = Column(Text, nullable=True)

    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    candidate = relationship("ContentImportCandidate", back_populates="ai_analysis_runs")
    parent_run = relationship("ContentAIAnalysisRun", remote_side=[id], backref="child_runs")

    __table_args__ = (
        Index("idx_ai_run_candidate_attempt", "candidate_id", "attempt_no"),
        Index("idx_ai_run_status", "status"),
        Index("idx_ai_run_gate", "gate"),
        Index("idx_ai_run_disposition", "human_disposition"),
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


class PaperTemplate(Base):
    """组卷规则模板（复用配置）：题型配比 / 难度分布 / 知识点覆盖 / 随机种子。

    config 结构（v1）：
    {
      "total": 10,
      "type_mix": {"choice": 4, "judge": 3, "numeric_fill": 3},
      "difficulty": {"1": 3, "2": 4, "3": 3},   # 可选，软约束
      "kp_codes": ["function-definition"],       # 可选，硬过滤
      "random_seed": 42,
      "score_per_question": 10
    }
    """

    __tablename__ = "paper_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    course_id = Column(
        String(36), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    version_id = Column(
        String(36), ForeignKey("knowledge_graph_versions.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    config = Column(JSON, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    papers = relationship("Paper", back_populates="template")


class Paper(Base):
    """生成的试卷（组卷产物）。题目以快照写入 PaperQuestion，
    之后题库的编辑/退役不影响已生成试卷（题目快照，§WS-C）。"""

    __tablename__ = "papers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36), ForeignKey("paper_templates.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    title = Column(String(200), nullable=False)
    course_id = Column(String(36), nullable=True, index=True)
    version_id = Column(String(36), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="generated")
    random_seed = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    template = relationship("PaperTemplate", back_populates="papers")
    questions = relationship(
        "PaperQuestion", back_populates="paper", cascade="all, delete-orphan",
        order_by="PaperQuestion.position",
    )


class PaperQuestion(Base):
    """卷内题目快照：content/options/answer_spec/difficulty/知识点在生成时固化。"""

    __tablename__ = "paper_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id = Column(String(20), ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    position = Column(Integer, nullable=False)
    score = Column(Float, nullable=False, default=10)
    snapshot = Column(JSON, nullable=False)

    paper = relationship("Paper", back_populates="questions")


class PracticeSession(Base):
    """Owner-bound, immutable-question-set practice session.

    This is intentionally separate from ``Paper``: Paper remains an internal/admin
    composition artifact while a PracticeSession is a student learning fact.
    """
    __tablename__ = "practice_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    mode = Column(String(20), nullable=False, default="practice")
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("knowledge_graph_versions.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="created", index=True)
    config_snapshot = Column(JSON, nullable=False)
    random_seed = Column(Integer, nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    duration_limit_seconds = Column(Integer, nullable=True)
    completion_reason = Column(String(30), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    questions = relationship("PracticeSessionQuestion", back_populates="session", cascade="all, delete-orphan", order_by="PracticeSessionQuestion.position")
    attempts = relationship("PracticeAttempt", back_populates="session", cascade="all, delete-orphan")
    blueprint = relationship("AssessmentBlueprint", back_populates="session", uselist=False, cascade="all, delete-orphan")
    draft_answers = relationship("AssessmentDraftAnswer", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_practice_session_owner_idempotency"),
        Index("ix_practice_session_owner_status", "user_id", "status"),
    )


class PracticeSessionQuestion(Base):
    __tablename__ = "practice_session_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(20), ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    position = Column(Integer, nullable=False)
    score = Column(Float, nullable=False, default=1)
    snapshot = Column(JSON, nullable=False)

    session = relationship("PracticeSession", back_populates="questions")

    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_practice_session_position"),
        UniqueConstraint("session_id", "question_id", name="uq_practice_session_question"),
    )


class PracticeAttempt(Base):
    """An immutable, immediately graded practice submission."""
    __tablename__ = "practice_attempts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    session_question_id = Column(Integer, ForeignKey("practice_session_questions.id", ondelete="RESTRICT"), nullable=False)
    question_id = Column(String(20), ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    user_answer = Column(JSON, nullable=True)
    correct = Column(Boolean, nullable=False)
    grading_snapshot = Column(JSON, nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("PracticeSession", back_populates="attempts")

    __table_args__ = (
        UniqueConstraint("session_question_id", name="uq_practice_attempt_session_question"),
        UniqueConstraint("user_id", "session_id", "idempotency_key", name="uq_practice_attempt_idempotency"),
    )


class UserKnowledgeState(Base):
    """Deterministic, rebuildable mastery projection derived from attempts."""
    __tablename__ = "user_knowledge_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    knowledge_point_code = Column(String(100), nullable=False)
    attempts_count = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    mastery = Column(Float, nullable=False, default=0.0)
    last_attempt_id = Column(String(36), ForeignKey("practice_attempts.id", ondelete="SET NULL"), nullable=True)
    last_practiced_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "knowledge_point_code", name="uq_user_knowledge_state_owner_code"),
        Index("ix_user_knowledge_state_owner_mastery", "user_id", "mastery"),
    )


class ReviewSchedule(Base):
    """Owner-bound spaced-review projection; safe to rebuild from attempts."""
    __tablename__ = "review_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    knowledge_point_code = Column(String(100), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    interval_days = Column(Integer, nullable=False, default=1)
    consecutive_correct = Column(Integer, nullable=False, default=0)
    last_attempt_id = Column(String(36), ForeignKey("practice_attempts.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "knowledge_point_code", name="uq_review_schedule_owner_code"),
        Index("ix_review_schedule_owner_due", "user_id", "due_at"),
    )


class AssessmentBlueprint(Base):
    """Auditable assessment plan; never contains question bodies or answers."""
    __tablename__ = "assessment_blueprints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    schema_version = Column(String(20), nullable=False, default="1")
    prompt_version = Column(String(40), nullable=False)
    model = Column(String(100), nullable=True)
    planning_source = Column(String(30), nullable=False)
    input_signal_snapshot = Column(JSON, nullable=False)
    blueprint_json = Column(JSON, nullable=False)
    deviations_json = Column(JSON, nullable=False, default=list)
    latency_ms = Column(Integer, nullable=True)
    token_usage = Column(JSON, nullable=True)
    error_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("PracticeSession", back_populates="blueprint")


class AssessmentDraftAnswer(Base):
    __tablename__ = "assessment_draft_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    session_question_id = Column(Integer, ForeignKey("practice_session_questions.id", ondelete="CASCADE"), nullable=False)
    answer = Column(JSON, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("PracticeSession", back_populates="draft_answers")

    __table_args__ = (
        UniqueConstraint("session_id", "session_question_id", name="uq_assessment_draft_question"),
    )


class QuestionAuditLog(Base):
    """正式题目状态审计（P0-8）：每次审核/发布/退役等状态变化留痕。

    action：reviewed / published / retired / edited
    details：可选快照/差异（如发布时写入的能力字段派生结果）。
    """

    __tablename__ = "question_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(
        String(20), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action = Column(String(30), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    operator_id = Column(String(36), nullable=True)
    reason = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    __table_args__ = (
        Index("idx_qa_question_created", "question_id", "created_at"),
    )


class ContentTask(Base):
    """异步内容任务（P0-1/2）：导入解析 / AI 批量分析的持久化执行记录。

    status 状态机：pending → running → succeeded / partially_succeeded / failed / cancelled
                 running 失败且可重试 → retrying → running（next_run_at 到期）
    字段承载进度（progress JSON）：total / done / success / doubtful / failed / current / errors
    多 Worker 安全：claim 采用条件 UPDATE（status ∈ pending/retrying 且到期），同一任务只会被一个 Worker 认领。
    """

    __tablename__ = "content_tasks"

    id = Column(String(36), primary_key=True)
    kind = Column(String(30), nullable=False, index=True)  # import_parse / ai_batch_analyze
    ref_id = Column(String(36), nullable=False, index=True)  # 关联业务对象（batch_id）
    status = Column(String(20), nullable=False, default="pending", index=True)
    payload = Column(JSON, nullable=True)
    progress = Column(JSON, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=0)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    worker_id = Column(String(64), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_ct_claim", "status", "next_run_at"),
        Index("idx_ct_kind_ref", "kind", "ref_id"),
    )
