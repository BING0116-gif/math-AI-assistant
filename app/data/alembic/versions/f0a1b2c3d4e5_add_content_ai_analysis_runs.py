"""add content_ai_analysis_runs + questions.ai_provider

Step 1.1-E2-A0: three-stage AI content pipeline (Document Import → AI Analysis → Review).

Adds:
- content_ai_analysis_runs: one AI analysis run fact per candidate
  (pending → analyzing → validating → verifying → pass/doubtful/failed),
  with analysis_json / verifier_json / gate / gate_reasons,
  attempt_no / parent_run_id (reanalysis lineage), human_disposition / human_note,
  error_code / error_message, started_at / completed_at.
  - candidate_id → content_import_candidates.id RESTRICT (delete policy: provenance SAFE)
  - parent_run_id → content_ai_analysis_runs.id RESTRICT (self-ref lineage)
- questions.ai_provider: nullable; marks which AI provider produced the
  structured enrichment. 'mock' results are blocked from formal publishing.

Delete policy: RESTRICT everywhere so an AI audit record cannot be physically
dropped when its candidate / parent run still exists.

Revision ID: f0a1b2c3d4e5
Revises: ab12cd34ef56
"""

import sqlalchemy as sa

from alembic import op


revision = "f0a1b2c3d4e5"
down_revision = "ab12cd34ef56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_ai_analysis_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False, server_default="mock"),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("gate", sa.String(20), nullable=True),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("verifier_json", sa.JSON(), nullable=True),
        sa.Column("gate_reasons", sa.JSON(), nullable=True),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_run_id", sa.String(36), nullable=True),
        sa.Column("human_disposition", sa.String(20), nullable=True),
        sa.Column("human_note", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["content_import_candidates.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"], ["content_ai_analysis_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_run_candidate", "content_ai_analysis_runs", ["candidate_id"])
    op.create_index(
        "ix_ai_run_candidate_attempt",
        "content_ai_analysis_runs",
        ["candidate_id", "attempt_no"],
    )
    op.create_index("ix_ai_run_status", "content_ai_analysis_runs", ["status"])
    op.create_index("ix_ai_run_gate", "content_ai_analysis_runs", ["gate"])
    op.create_index("ix_ai_run_disposition", "content_ai_analysis_runs", ["human_disposition"])
    op.create_index("ix_ai_run_parent", "content_ai_analysis_runs", ["parent_run_id"])
    op.create_index("ix_ai_run_provider", "content_ai_analysis_runs", ["provider"])

    # questions.ai_provider (nullable; marks mock enrichment so publish can block it)
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("ai_provider", sa.String(30), nullable=True))
        batch.create_index("ix_questions_ai_provider", ["ai_provider"])


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_index("ix_questions_ai_provider")
        batch.drop_column("ai_provider")

    op.drop_index("ix_ai_run_provider", table_name="content_ai_analysis_runs")
    op.drop_index("ix_ai_run_disposition", table_name="content_ai_analysis_runs")
    op.drop_index("ix_ai_run_gate", table_name="content_ai_analysis_runs")
    op.drop_index("ix_ai_run_status", table_name="content_ai_analysis_runs")
    op.drop_index("ix_ai_run_candidate_attempt", table_name="content_ai_analysis_runs")
    op.drop_index("ix_ai_run_candidate", table_name="content_ai_analysis_runs")
    op.drop_table("content_ai_analysis_runs")
