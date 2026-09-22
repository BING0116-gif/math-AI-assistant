"""add learning resource provenance and review governance

Revision ID: d2e3f4a5b6c7
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_point_resources") as batch_op:
        batch_op.add_column(sa.Column("source_document_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("external_key", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("source_locator", sa.String(300), nullable=True))
        batch_op.add_column(sa.Column("content_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("math_validation_status", sa.String(20), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("reviewed_by", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_kp_resource_source_document", "source_documents", ["source_document_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_unique_constraint("uq_kp_resource_external_key", ["external_key"])
        batch_op.create_index("ix_kp_resource_source_document", ["source_document_id"])
        batch_op.create_index("ix_kp_resource_content_hash", ["content_hash"])


def downgrade() -> None:
    with op.batch_alter_table("knowledge_point_resources") as batch_op:
        batch_op.drop_index("ix_kp_resource_content_hash")
        batch_op.drop_index("ix_kp_resource_source_document")
        batch_op.drop_constraint("uq_kp_resource_external_key", type_="unique")
        batch_op.drop_constraint("fk_kp_resource_source_document", type_="foreignkey")
        for name in (
            "published_at", "reviewed_at", "reviewed_by", "math_validation_status",
            "content_hash", "source_locator", "external_key", "source_document_id",
        ):
            batch_op.drop_column(name)
