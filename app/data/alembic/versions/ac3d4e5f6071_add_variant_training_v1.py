"""add variant training v1

Revision ID: ac3d4e5f6071
Revises: ab2c3d4e5f60
"""
import sqlalchemy as sa
from alembic import op

revision = "ac3d4e5f6071"
down_revision = "ab2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("variant_blueprint", sa.JSON(), nullable=True))
    op.create_table(
        "variant_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("error_item_id", sa.Integer(), nullable=False),
        sa.Column("source_question_id", sa.String(20), nullable=False),
        sa.Column("generated_question_id", sa.String(20), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("variation_dimensions", sa.JSON(), nullable=False),
        sa.Column("template_version", sa.String(40), nullable=False),
        sa.Column("generation_provider", sa.String(80), nullable=False),
        sa.Column("generation_model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("duplicate_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["error_item_id"], ["error_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("generated_question_id", name="uq_variant_generation_question"),
        sa.UniqueConstraint("session_id", name="uq_variant_generation_session"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_variant_generation_owner_idem"),
        sa.UniqueConstraint("user_id", "duplicate_fingerprint", name="uq_variant_generation_owner_fingerprint"),
    )
    op.create_index("ix_variant_generation_user_id", "variant_generations", ["user_id"])
    op.create_index("ix_variant_generation_error_item_id", "variant_generations", ["error_item_id"])
    op.create_index("ix_variant_generation_source_question_id", "variant_generations", ["source_question_id"])
    op.create_index("ix_variant_generation_duplicate_fingerprint", "variant_generations", ["duplicate_fingerprint"])
    op.create_index("ix_variant_generation_owner_created", "variant_generations", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("variant_generations")
    op.drop_column("questions", "variant_blueprint")
