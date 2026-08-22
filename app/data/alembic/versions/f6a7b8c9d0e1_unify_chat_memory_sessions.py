"""add user-scoped external chat session identity

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(sa.Column("external_session_id", sa.String(128), nullable=True))
    op.execute("UPDATE chat_sessions SET external_session_id = id WHERE external_session_id IS NULL")
    with op.batch_alter_table("chat_sessions") as batch:
        batch.alter_column("external_session_id", existing_type=sa.String(128), nullable=False)
        batch.create_index("ix_chat_sessions_external_session_id", ["external_session_id"])
        batch.create_unique_constraint(
            "uq_chat_session_user_external", ["user_id", "external_session_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_constraint("uq_chat_session_user_external", type_="unique")
        batch.drop_index("ix_chat_sessions_external_session_id")
        batch.drop_column("external_session_id")
