"""T07: add auditable memory and profile evidence edges

Revision ID: b8d9e0f1a2b3
Revises: b7c8d9e0f1a2
"""
import sqlalchemy as sa
from alembic import op

revision = "b8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("memory_id", sa.Integer(), nullable=False),
        sa.Column("learning_record_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learning_record_id"], ["learning_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_id", "learning_record_id", name="uq_memory_evidence_edge"),
    )
    op.create_index(
        "ix_memory_evidence_owner_memory",
        "memory_evidence",
        ["user_id", "memory_id"],
    )

    op.create_table(
        "profile_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("dimension", sa.String(length=100), nullable=False),
        sa.Column("memory_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_snapshot_id",
            "dimension",
            "memory_id",
            name="uq_profile_evidence_edge",
        ),
    )
    op.create_index(
        "ix_profile_evidence_owner_dimension",
        "profile_evidence",
        ["user_id", "dimension", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_profile_evidence_owner_dimension", table_name="profile_evidence")
    op.drop_table("profile_evidence")
    op.drop_index("ix_memory_evidence_owner_memory", table_name="memory_evidence")
    op.drop_table("memory_evidence")
