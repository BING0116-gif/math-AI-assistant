"""Reconcile indexes and nullability declared by the current ORM models."""
from alembic import op
import sqlalchemy as sa

revision = "hi60718293a7"
down_revision = "gh60718293a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Names below are the historical names emitted by the earlier revisions.
    op.drop_index("ix_async_task_status", table_name="async_tasks")
    op.create_index("ix_async_tasks_status", "async_tasks", ["status"])
    op.drop_index("ix_outbox_lease_claim", table_name="outbox_events")
    op.create_index("ix_mastery_correction_events_knowledge_point_code", "mastery_correction_events", ["knowledge_point_code"])
    op.create_index("ix_mastery_correction_events_user_id", "mastery_correction_events", ["user_id"])
    op.create_index("ix_subjective_evaluations_user_id", "subjective_evaluations", ["user_id"])
    # This migration was previously run on some installations before a later
    # statement failed.  Keep the constraint creation idempotent so retrying
    # Alembic does not fail on the already-created object.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'courses_code_key'
                  AND conrelid = 'courses'::regclass
            ) THEN
                ALTER TABLE courses ADD CONSTRAINT courses_code_key UNIQUE (code);
            END IF;
        END $$
        """))
    else:
        recreate = "always"
        with op.batch_alter_table("courses", recreate=recreate) as batch:
            batch.create_unique_constraint("courses_code_key", ["code"])
    # Existing installations may contain legacy NULL roles. Normalize before
    # enforcing the ORM's non-null ownership invariant.
    op.execute(sa.text("UPDATE users SET role = 'student' WHERE role IS NULL"))
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "never"
    with op.batch_alter_table("users", recreate=recreate) as batch:
        batch.alter_column("role", existing_type=sa.String(length=20), nullable=False)


def downgrade() -> None:
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "never"
    with op.batch_alter_table("users", recreate=recreate) as batch:
        batch.alter_column("role", existing_type=sa.String(length=20), nullable=True)
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE courses DROP CONSTRAINT IF EXISTS courses_code_key"))
    else:
        with op.batch_alter_table("courses", recreate="always") as batch:
            batch.drop_constraint("courses_code_key", type_="unique")
    op.drop_index("ix_subjective_evaluations_user_id", table_name="subjective_evaluations")
    op.drop_index("ix_mastery_correction_events_user_id", table_name="mastery_correction_events")
    op.drop_index("ix_mastery_correction_events_knowledge_point_code", table_name="mastery_correction_events")
    op.create_index("ix_outbox_lease_claim", "outbox_events", ["status", "lease_until", "available_at"])
    op.drop_index("ix_async_tasks_status", table_name="async_tasks")
    op.create_index("ix_async_task_status", "async_tasks", ["status"])
