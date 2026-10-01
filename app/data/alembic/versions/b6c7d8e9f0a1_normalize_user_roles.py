"""Normalize persisted user roles for the RBAC v1 surface."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve teacher for forward compatibility; all other unexpected values
    # are made safe by treating them as student accounts.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET role = 'student'
            WHERE role IS NULL
               OR role NOT IN ('student', 'teacher', 'admin')
            """
        )
    )
    # Align the column constraint with the model (nullable=False). The initial
    # migration created users.role as nullable; SQLite dev databases skip the
    # ALTER because SQLite cannot SET NOT NULL without a table rebuild.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE users ALTER COLUMN role SET NOT NULL"))


def downgrade() -> None:
    # Role normalization is intentionally not reversed: converting safe values
    # back to unknown roles would weaken authorization guarantees. Dropping
    # the NOT NULL constraint only widens the column and is safe to undo.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE users ALTER COLUMN role DROP NOT NULL"))
