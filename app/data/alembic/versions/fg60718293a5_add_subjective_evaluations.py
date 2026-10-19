"""Task 3.3 immutable subjective scoring evidence."""
from alembic import op
import sqlalchemy as sa

revision = "fg60718293a5"
# Reconcile the repository's three pre-existing migration heads while adding
# the Task 3.3 table; this keeps fresh databases on one deterministic head.
down_revision = ("a1b2c3d4e5f7", "ab5f60718294")
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "subjective_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(20), sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("practice_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("answer_snapshot", sa.Text(), nullable=False),
        sa.Column("reference_snapshot", sa.JSON(), nullable=False),
        sa.Column("dimension_scores", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="not_required"),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("verdict IN ('certainly_correct','probably_correct','needs_human_review','unable_to_determine')", name="ck_subjective_eval_verdict"),
        sa.CheckConstraint("review_status IN ('not_required','pending','resolved')", name="ck_subjective_eval_review_status"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_subjective_eval_owner_idem"),
    )
    op.create_index("ix_subjective_eval_owner_question", "subjective_evaluations", ["user_id", "question_id", "created_at"])
    op.create_index("ix_subjective_evaluations_question_id", "subjective_evaluations", ["question_id"])
    op.create_index("ix_subjective_evaluations_attempt_id", "subjective_evaluations", ["attempt_id"])

def downgrade():
    op.drop_table("subjective_evaluations")
