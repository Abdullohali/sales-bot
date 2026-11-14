"""bot_users: per-user language

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12 19:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bot_users',
        sa.Column('tg_id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('lang', sa.String(length=5), nullable=False),
        sa.PrimaryKeyConstraint('tg_id'),
    )


def downgrade() -> None:
    op.drop_table('bot_users')
