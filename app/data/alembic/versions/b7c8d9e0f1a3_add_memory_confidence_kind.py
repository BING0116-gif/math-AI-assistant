"""add memory confidence and kind

Revision ID: b7c8d9e0f1a3
Revises: fb2c3d4e5f60
Create Date: 2026-10-04

阶段四 6.2:Memory 增加 confidence/memory_kind/last_confirmed_at/superseded_by/
conflict_status。server_default 保证存量行回填;downgrade 全部 drop(外键列先删)。
superseded_by 带自引用外键,SQLite 方言走 batch 复制模式(其余方言为普通 ALTER)。
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a3"
down_revision = "fb2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("memories", sa.Column("confidence", sa.Float(), nullable=False, server_default="0.6"))
    op.add_column("memories", sa.Column("memory_kind", sa.String(32), nullable=False, server_default="context"))
    op.add_column("memories", sa.Column("last_confirmed_at", sa.Integer(), nullable=True))
    with op.batch_alter_table("memories") as batch:
        batch.add_column(
            sa.Column(
                "superseded_by",
                sa.Integer(),
                sa.ForeignKey("memories.id", ondelete="SET NULL", name="fk_memories_superseded_by"),
                nullable=True,
            )
        )
    op.add_column("memories", sa.Column("conflict_status", sa.String(16), nullable=False, server_default="none"))
    op.create_index("idx_mem_user_kind_status", "memories", ["user_id", "memory_kind", "status"])


def downgrade():
    op.drop_index("idx_mem_user_kind_status", table_name="memories")
    op.drop_column("memories", "conflict_status")
    with op.batch_alter_table("memories") as batch:
        batch.drop_column("superseded_by")
    op.drop_column("memories", "last_confirmed_at")
    op.drop_column("memories", "memory_kind")
    op.drop_column("memories", "confidence")
