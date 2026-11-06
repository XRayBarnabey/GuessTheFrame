"""track game inactivity

Revision ID: 8577c58c8e93
Revises: 8f8fd9246b53
Create Date: 2026-11-06 13:12:17.191713
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '8577c58c8e93'
down_revision: str | None = '8f8fd9246b53'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_activity_at', sa.DateTime(), nullable=True))
    # Existing in-progress games get a fresh inactivity window at upgrade time.
    op.execute(
        "UPDATE games SET last_activity_at = CURRENT_TIMESTAMP "
        "WHERE status = 'in_progress' AND last_activity_at IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_column('last_activity_at')
