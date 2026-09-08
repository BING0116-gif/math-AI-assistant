"""add error item aggregation and review workflow

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode keeps the migration valid for the explicitly configured local
    # SQLite development database as well as the production PostgreSQL target.
    with op.batch_alter_table("error_items") as batch:
        batch.add_column(sa.Column("question_id", sa.String(20), nullable=True))
        batch.add_column(sa.Column("source", sa.String(20), nullable=False, server_default="manual"))
        batch.add_column(sa.Column("structure_confidence", sa.Float(), nullable=False, server_default="0.5"))
        batch.add_column(sa.Column("review_state", sa.String(20), nullable=False, server_default="new"))
        batch.add_column(sa.Column("knowledge_point_codes", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("wrong_attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_attempt_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_error_items_question", "questions", ["question_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_error_items_last_attempt", "practice_attempts", ["last_attempt_id"], ["id"], ondelete="SET NULL")
        batch.create_unique_constraint("uq_error_item_owner_question", ["user_id", "question_id"])
        batch.create_index("ix_error_items_owner_state", ["user_id", "review_state"])
    op.create_table(
        "error_review_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(128), nullable=False, unique=True),
        sa.Column("error_item_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("attempt_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("from_state", sa.String(20), nullable=False),
        sa.Column("to_state", sa.String(20), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["error_item_id"], ["error_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["practice_attempts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_error_review_owner_item_time", "error_review_events", ["user_id", "error_item_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_error_review_owner_item_time", table_name="error_review_events")
    op.drop_table("error_review_events")
    with op.batch_alter_table("error_items") as batch:
        batch.drop_index("ix_error_items_owner_state")
        batch.drop_constraint("uq_error_item_owner_question", type_="unique")
        batch.drop_constraint("fk_error_items_last_attempt", type_="foreignkey")
        batch.drop_constraint("fk_error_items_question", type_="foreignkey")
        for name in ("last_reviewed_at", "last_attempt_id", "wrong_attempt_count", "knowledge_point_codes", "review_state", "structure_confidence", "source", "question_id"):
            batch.drop_column(name)
