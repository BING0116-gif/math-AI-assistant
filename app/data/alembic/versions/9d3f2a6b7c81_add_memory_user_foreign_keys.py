"""add memory and profile user foreign keys

Revision ID: 9d3f2a6b7c81
Revises: 7824223d8a63
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "9d3f2a6b7c81"
down_revision = "7824223d8a63"
branch_labels = None
depends_on = None


def _assert_no_orphans(table_name: str) -> None:
    connection = op.get_bind()
    orphan_count = connection.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM {table_name} AS child
            LEFT JOIN users ON users.id = child.user_id
            WHERE child.user_id IS NULL
               OR LENGTH(child.user_id) > 36
               OR users.id IS NULL
            """
        )
    ).scalar_one()
    if orphan_count:
        raise RuntimeError(
            f"{table_name} contains {orphan_count} orphaned or invalid user_id values; "
            "audit and repair them before retrying this migration"
        )


def upgrade() -> None:
    _assert_no_orphans("memories")
    _assert_no_orphans("user_profiles")

    with op.batch_alter_table("memories") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=36),
            existing_nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_memories_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=36),
            existing_nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_user_profiles_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.drop_constraint(
            "fk_user_profiles_user_id_users", type_="foreignkey"
        )
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=36),
            type_=sa.String(length=64),
            existing_nullable=False,
        )

    with op.batch_alter_table("memories") as batch_op:
        batch_op.drop_constraint("fk_memories_user_id_users", type_="foreignkey")
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=36),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
