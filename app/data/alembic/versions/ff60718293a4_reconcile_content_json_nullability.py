"""reconcile content JSON nullability with ORM models

Revision ID: ff60718293a4
Revises: fe5f60718293
"""

from alembic import op
import sqlalchemy as sa


revision = "ff60718293a4"
down_revision = "fe5f60718293"
branch_labels = None
depends_on = None


def _backfill_nulls() -> None:
    """Normalize legacy NULL JSON values before adding NOT NULL constraints."""
    analysis_runs = sa.table(
        "content_ai_analysis_runs",
        sa.column("gate_reasons", sa.JSON()),
    )
    candidates = sa.table(
        "content_import_candidates",
        sa.column("warnings", sa.JSON()),
        sa.column("suggested_knowledge_point_codes", sa.JSON()),
    )
    batches = sa.table(
        "import_batches",
        sa.column("stats", sa.JSON()),
    )

    op.execute(
        analysis_runs.update()
        .where(analysis_runs.c.gate_reasons.is_(None))
        .values(gate_reasons=[])
    )
    op.execute(
        candidates.update()
        .where(candidates.c.warnings.is_(None))
        .values(warnings=[])
    )
    op.execute(
        candidates.update()
        .where(candidates.c.suggested_knowledge_point_codes.is_(None))
        .values(suggested_knowledge_point_codes=[])
    )
    op.execute(
        batches.update()
        .where(batches.c.stats.is_(None))
        .values(stats={})
    )


def upgrade() -> None:
    _backfill_nulls()

    with op.batch_alter_table("content_ai_analysis_runs") as batch:
        batch.alter_column(
            "gate_reasons",
            existing_type=sa.JSON(),
            nullable=False,
        )

    with op.batch_alter_table("content_import_candidates") as batch:
        batch.alter_column(
            "warnings",
            existing_type=sa.JSON(),
            nullable=False,
        )
        batch.alter_column(
            "suggested_knowledge_point_codes",
            existing_type=sa.JSON(),
            nullable=False,
        )

    with op.batch_alter_table("import_batches") as batch:
        batch.alter_column(
            "stats",
            existing_type=sa.JSON(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("import_batches") as batch:
        batch.alter_column(
            "stats",
            existing_type=sa.JSON(),
            nullable=True,
        )

    with op.batch_alter_table("content_import_candidates") as batch:
        batch.alter_column(
            "suggested_knowledge_point_codes",
            existing_type=sa.JSON(),
            nullable=True,
        )
        batch.alter_column(
            "warnings",
            existing_type=sa.JSON(),
            nullable=True,
        )

    with op.batch_alter_table("content_ai_analysis_runs") as batch:
        batch.alter_column(
            "gate_reasons",
            existing_type=sa.JSON(),
            nullable=True,
        )
