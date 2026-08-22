"""add content_tasks

P0-1/2：异步内容任务持久化表。导入解析（MinerU）与 AI 批量分析从
进程内（内存字典 / asyncio.create_task）迁移到 DB 任务表 + 独立 Worker：
- 上传/批分析接口立即返回 task_id，Worker 后台执行
- 状态机：pending → running → succeeded / partially_succeeded / failed / cancelled
          运行失败可重试 → retrying → running（next_run_at 到期）
- 多实例安全：条件 UPDATE 认领（status ∈ pending/retrying 且到期）
- 进度/心跳：progress JSON + heartbeat_at（僵尸任务检测）

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7
"""

import sqlalchemy as sa

from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("ref_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_tasks_status", "content_tasks", ["status"])
    op.create_index("ix_content_tasks_kind", "content_tasks", ["kind"])
    op.create_index("ix_content_tasks_ref_id", "content_tasks", ["ref_id"])
    op.create_index("ix_content_tasks_created_at", "content_tasks", ["created_at"])
    op.create_index("ix_content_tasks_next_run_at", "content_tasks", ["next_run_at"])
    op.create_index("ix_ct_claim", "content_tasks", ["status", "next_run_at"])
    op.create_index("ix_ct_kind_ref", "content_tasks", ["kind", "ref_id"])


def downgrade() -> None:
    op.drop_index("ix_ct_kind_ref", table_name="content_tasks")
    op.drop_index("ix_ct_claim", table_name="content_tasks")
    op.drop_index("ix_content_tasks_next_run_at", table_name="content_tasks")
    op.drop_index("ix_content_tasks_created_at", table_name="content_tasks")
    op.drop_index("ix_content_tasks_ref_id", table_name="content_tasks")
    op.drop_index("ix_content_tasks_kind", table_name="content_tasks")
    op.drop_index("ix_content_tasks_status", table_name="content_tasks")
    op.drop_table("content_tasks")
