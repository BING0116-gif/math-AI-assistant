"""T15 add owner-bound animation job, event and artifact tables.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
"""
import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "animation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("template_source_sha256", sa.String(64), nullable=False),
        sa.Column("renderer_image_digest", sa.String(128), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False, server_default="user_explicit"),
        sa.Column("admission_snapshot", sa.JSON(), nullable=False),
        sa.Column("visual_spec_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(40), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cache_key", sa.String(64), nullable=True),
        sa.Column("fallback_kind", sa.String(40), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_animation_job_owner_idem"),
        sa.CheckConstraint("status IN ('pending','running','succeeded','fallback','failed','cancelled')", name="ck_animation_job_status"),
        sa.CheckConstraint("trigger IN ('user_explicit','teaching_strategy')", name="ck_animation_job_trigger"),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts BETWEEN 1 AND 2 AND attempt_count <= max_attempts", name="ck_animation_job_attempts"),
        sa.CheckConstraint("recovery_count >= 0", name="ck_animation_job_recovery"),
        sa.CheckConstraint("length(request_fingerprint) = 64 AND length(template_source_sha256) = 64", name="ck_animation_job_hashes"),
        sa.CheckConstraint("length(renderer_image_digest) BETWEEN 71 AND 128", name="ck_animation_job_renderer_digest"),
    )
    op.create_index("ix_animation_job_claim", "animation_jobs", ["status", "lease_expires_at", "created_at"])
    op.create_index("ix_animation_job_owner_created", "animation_jobs", ["user_id", "created_at"])

    op.create_table(
        "animation_job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("animation_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "sequence", name="uq_animation_event_job_sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_animation_event_sequence"),
        sa.CheckConstraint("status IN ('pending','running','succeeded','fallback','failed','cancelled')", name="ck_animation_event_status"),
    )
    op.create_index("ix_animation_event_job_created", "animation_job_events", ["job_id", "created_at"])

    op.create_table(
        "animation_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("animation_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("frame_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("validation_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", "kind", name="uq_animation_artifact_job_kind"),
        sa.CheckConstraint("kind IN ('video','thumbnail','gif')", name="ck_animation_artifact_kind"),
        sa.CheckConstraint("validation_status IN ('pending','validated','rejected')", name="ck_animation_artifact_validation"),
        sa.CheckConstraint("length(sha256) = 64 AND size_bytes >= 0", name="ck_animation_artifact_integrity"),
    )
    op.create_index("ix_animation_artifact_owner_job_kind", "animation_artifacts", ["user_id", "job_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_animation_artifact_owner_job_kind", table_name="animation_artifacts")
    op.drop_table("animation_artifacts")
    op.drop_index("ix_animation_event_job_created", table_name="animation_job_events")
    op.drop_table("animation_job_events")
    op.drop_index("ix_animation_job_owner_created", table_name="animation_jobs")
    op.drop_index("ix_animation_job_claim", table_name="animation_jobs")
    op.drop_table("animation_jobs")
