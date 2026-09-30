"""add note library filter metadata

Revision ID: f1a2b3c4d5e6
Revises: fa1b2c3d4e5f
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "fa1b2c3d4e5f"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("study_notes") as batch:
        batch.add_column(sa.Column("primary_course_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("primary_knowledge_point_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_study_notes_primary_course", "courses", ["primary_course_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_study_notes_primary_kp", "knowledge_points", ["primary_knowledge_point_id"], ["id"], ondelete="SET NULL")
        batch.drop_constraint("ck_study_note_status", type_="check")
        batch.create_check_constraint("ck_study_note_status", "status IN ('active','archived','deleted')")
    op.create_index("ix_study_note_owner_course", "study_notes", ["user_id", "primary_course_id"])
    op.create_index("ix_study_note_owner_kp", "study_notes", ["user_id", "primary_knowledge_point_id"])

def downgrade():
    op.drop_index("ix_study_note_owner_kp", table_name="study_notes")
    op.drop_index("ix_study_note_owner_course", table_name="study_notes")
    with op.batch_alter_table("study_notes") as batch:
        batch.drop_constraint("ck_study_note_status", type_="check")
        batch.create_check_constraint("ck_study_note_status", "status IN ('active','deleted')")
        batch.drop_constraint("fk_study_notes_primary_kp", type_="foreignkey")
        batch.drop_constraint("fk_study_notes_primary_course", type_="foreignkey")
        batch.drop_column("primary_knowledge_point_id")
        batch.drop_column("primary_course_id")
