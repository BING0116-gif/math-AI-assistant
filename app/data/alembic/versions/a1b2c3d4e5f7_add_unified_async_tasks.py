"""add canonical asynchronous task lifecycle"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4

revision = "a1b2c3d4e5f7"
down_revision = "ff60718293a4"
branch_labels = None
depends_on = None

TASK_TABLES = ("content_tasks", "content_ai_analysis_runs", "outbox_events", "animation_jobs", "note_cleanup_tasks", "note_ai_runs")

def _canonical(status: str) -> str:
    if status in {"pending", "queued", "created"}: return "pending"
    if status in {"retrying"}: return "retryable_failed"
    if status in {"running", "processing", "analyzing", "validating", "verifying"}: return "running"
    if status in {"succeeded", "completed", "partially_succeeded", "fallback", "pass"}: return "succeeded"
    if status in {"cancelled", "canceled", "abandoned"}: return "cancelled"
    return "permanently_failed" if status in {"failed", "error", "dead", "doubtful"} else "pending"

def upgrade() -> None:
    op.create_table(
        "async_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("legacy_status", sa.String(40), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','running','succeeded','retryable_failed','permanently_failed','cancelled')", name="ck_async_task_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_async_task_attempts"),
        sa.UniqueConstraint("task_type", "idempotency_key", name="uq_async_task_type_idem"),
    )
    op.create_index("ix_async_task_status", "async_tasks", ["status"])
    op.create_index("ix_async_task_claim", "async_tasks", ["status", "lease_until", "queued_at"])
    op.create_index("ix_async_task_resource", "async_tasks", ["resource_type", "resource_id"])
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "never"
    for table in TASK_TABLES:
        # All supported production databases can add this nullable column and
        # FK in place.  Rebuilding self-referencing tables (notably
        # content_ai_analysis_runs) fails because the temporary table's FK is
        # created before its primary-key uniqueness is available.
        with op.batch_alter_table(table, recreate=recreate) as batch:
            batch.add_column(sa.Column("task_id", sa.String(36), nullable=True))
            batch.create_foreign_key(f"fk_{table}_async_task", "async_tasks", ["task_id"], ["id"], ondelete="SET NULL")
            batch.create_index(f"ix_{table}_task_id", ["task_id"])
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    for table in TASK_TABLES:
        rows = bind.execute(sa.text(f"SELECT id, status FROM {table} WHERE task_id IS NULL")).mappings()
        for row in rows:
            task_id = str(uuid4())
            status = row["status"] or "pending"
            bind.execute(sa.text("""INSERT INTO async_tasks
                (id, task_type, resource_type, resource_id, status, legacy_status, attempts, created_at, updated_at)
                VALUES (:id, :type, :resource_type, :resource_id, :status, :legacy, 0, :created, :updated)"""),
                {"id": task_id, "type": table, "resource_type": table, "resource_id": str(row["id"]), "status": _canonical(status), "legacy": status, "created": now, "updated": now})
            bind.execute(sa.text(f"UPDATE {table} SET task_id = :task_id WHERE id = :id"), {"task_id": task_id, "id": row["id"]})

def downgrade() -> None:
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "never"
    for table in reversed(TASK_TABLES):
        with op.batch_alter_table(table, recreate=recreate) as batch:
            batch.drop_index(f"ix_{table}_task_id")
            batch.drop_constraint(f"fk_{table}_async_task", type_="foreignkey")
            batch.drop_column("task_id")
    op.drop_index("ix_async_task_resource", table_name="async_tasks")
    op.drop_index("ix_async_task_claim", table_name="async_tasks")
    op.drop_index("ix_async_task_status", table_name="async_tasks")
    op.drop_table("async_tasks")
