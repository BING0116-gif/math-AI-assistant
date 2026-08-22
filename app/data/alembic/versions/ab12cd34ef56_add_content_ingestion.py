"""add content ingestion (source_documents / import_batches / content_import_candidates)

Step 1.1-C2: PDF → MinerU → Candidate → Question(draft) minimal formal chain.

Adds:
- source_documents: original document fact (metadata only, no PDF binary)
- import_batches: one parse run over a source document (pending/parsing/parsed/
  failed/completed) with idempotency_key unique per created_by
- content_import_candidates: ingestion staging records (NOT a second Question domain)
- questions.source_candidate_id: nullable UNIQUE FK to candidate (minimal provenance)

Delete policy: RESTRICT everywhere so a candidate that produced a Question,
its batch, and its source document cannot be physically deleted (provenance SAFE).

Revision ID: ab12cd34ef56
Revises: e1f2a3b4c5d6
"""

import sqlalchemy as sa

from alembic import op


revision = "ab12cd34ef56"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False, server_default="application/pdf"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_documents_sha256", "source_documents", ["sha256"])
    op.create_index("ix_source_documents_created_by", "source_documents", ["created_by"])
    op.create_index("ix_source_doc_created_by", "source_documents", ["created_by", "created_at"])

    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_document_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("parser_name", sa.String(50), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("created_by", "idempotency_key", name="uq_import_batch_idem"),
    )
    op.create_index("ix_import_batches_status", "import_batches", ["status"])
    op.create_index("ix_import_batches_created_by", "import_batches", ["created_by"])
    op.create_index("ix_import_batches_created_at", "import_batches", ["created_at"])
    op.create_index("ix_import_batch_source", "import_batches", ["source_document_id", "status"])

    op.create_table(
        "content_import_candidates",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("candidate_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_page_start", sa.Integer(), nullable=True),
        sa.Column("source_page_end", sa.Integer(), nullable=True),
        sa.Column("source_question_number", sa.String(50), nullable=True),
        sa.Column("raw_parsed_content", sa.Text(), nullable=True),
        sa.Column("stem", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("original_answer", sa.Text(), nullable=True),
        sa.Column("original_solution", sa.Text(), nullable=True),
        sa.Column("detected_question_type", sa.String(30), nullable=True),
        sa.Column("supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("suggested_knowledge_point_codes", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="parsed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidates_import_batch_id", "content_import_candidates", ["import_batch_id"])
    op.create_index("ix_candidate_batch_index", "content_import_candidates", ["import_batch_id", "candidate_index"])
    op.create_index("ix_candidate_status", "content_import_candidates", ["status"])

    # questions.source_candidate_id (nullable UNIQUE FK, minimal provenance)
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("source_candidate_id", sa.String(36), nullable=True))
        batch.create_index("ix_questions_source_candidate_id", ["source_candidate_id"], unique=True)
        batch.create_foreign_key(
            "fk_questions_source_candidate_id",
            "content_import_candidates",
            ["source_candidate_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_constraint("fk_questions_source_candidate_id", type_="foreignkey")
        batch.drop_index("ix_questions_source_candidate_id")
        batch.drop_column("source_candidate_id")

    op.drop_index("ix_candidate_status", table_name="content_import_candidates")
    op.drop_index("ix_candidate_batch_index", table_name="content_import_candidates")
    op.drop_index("ix_candidates_import_batch_id", table_name="content_import_candidates")
    op.drop_table("content_import_candidates")

    op.drop_index("ix_import_batch_source", table_name="import_batches")
    op.drop_index("ix_import_batches_created_at", table_name="import_batches")
    op.drop_index("ix_import_batches_created_by", table_name="import_batches")
    op.drop_index("ix_import_batches_status", table_name="import_batches")
    op.drop_table("import_batches")

    op.drop_index("ix_source_doc_created_by", table_name="source_documents")
    op.drop_index("ix_source_documents_created_by", table_name="source_documents")
    op.drop_index("ix_source_documents_sha256", table_name="source_documents")
    op.drop_table("source_documents")