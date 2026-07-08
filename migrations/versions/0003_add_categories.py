"""add_categories_table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-09 00:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'categories',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('image', sa.String(length=500), nullable=True),
        sa.Column('icon', sa.String(length=100), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('title')
    )
    op.add_column('bookings', sa.Column('isInstant', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('bookings', 'isInstant')
    op.drop_table('categories')
