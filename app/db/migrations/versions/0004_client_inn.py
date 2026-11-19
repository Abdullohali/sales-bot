"""clients.inn: taxpayer number (STIR / ИНН) of the buyer

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('inn', sa.String(length=14), nullable=True))
    op.create_index('ix_clients_inn', 'clients', ['inn'])


def downgrade() -> None:
    op.drop_index('ix_clients_inn', table_name='clients')
    op.drop_column('clients', 'inn')
