"""widen error item string fields used by automatic capture

Revision ID: a9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""

from alembic import op
import sqlalchemy as sa


revision = "a9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some deployed databases predate the canonical String(64) model and still
    # carry VARCHAR(30). UUID-backed automatic error items require 36 chars.
    with op.batch_alter_table("error_items") as batch:
        batch.alter_column(
            "item_id",
            existing_type=sa.String(length=30),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
        batch.alter_column(
            "added_at",
            existing_type=sa.String(length=30),
            type_=sa.String(length=64),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Do not truncate identifiers silently. A downgrade is permitted only when
    # every stored value fits the historical limit.
    connection = op.get_bind()
    longest_id = connection.execute(sa.text("SELECT max(length(item_id)) FROM error_items")).scalar()
    longest_added_at = connection.execute(sa.text("SELECT max(length(added_at)) FROM error_items")).scalar()
    if longest_id and longest_id > 30:
        raise RuntimeError("cannot narrow error_items.item_id while values exceed 30 characters")
    if longest_added_at and longest_added_at > 30:
        raise RuntimeError("cannot narrow error_items.added_at while values exceed 30 characters")
    with op.batch_alter_table("error_items") as batch:
        batch.alter_column(
            "item_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=30),
            existing_nullable=False,
        )
        batch.alter_column(
            "added_at",
            existing_type=sa.String(length=64),
            type_=sa.String(length=30),
            existing_nullable=True,
        )
