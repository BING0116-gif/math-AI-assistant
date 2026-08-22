"""drop redundant user_skills compatibility projection

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""
import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("user_skills")


def downgrade() -> None:
    op.create_table(
        "user_skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("skill_code", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100)),
        sa.Column("category_path", sa.String(200)),
        sa.Column("mastery_level", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="novice"),
        sa.Column("total_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True)),
        sa.Column("mastered_at", sa.DateTime(timezone=True)),
        sa.Column("evolution_history", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "skill_code", name="uq_user_skill"),
    )
    op.create_index("idx_us_user_mastery", "user_skills", ["user_id", "mastery_level"])
    op.create_index("idx_us_user_status", "user_skills", ["user_id", "status"])
    op.create_index("idx_us_skill_code", "user_skills", ["skill_code"])
