"""replace_otp_with_firebase

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-08 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add firebaseUid column
    op.add_column('users', sa.Column('firebaseUid', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_firebaseUid'), 'users', ['firebaseUid'], unique=True)
    
    # 2. Add updatedAt column
    # Use server_default of now() to populate it for existing rows
    op.add_column('users', sa.Column('updatedAt', sa.DateTime(), server_default=sa.text('now()'), nullable=False))
    
    # 3. Make email column nullable
    op.alter_column('users', 'email',
               existing_type=sa.String(length=255),
               nullable=True,
               existing_server_default=None)
               
    # 4. Drop verificationCode and otpExpiry columns
    op.drop_column('users', 'verificationCode')
    op.drop_column('users', 'otpExpiry')


def downgrade() -> None:
    # Re-add verificationCode and otpExpiry columns
    op.add_column('users', sa.Column('otpExpiry', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('verificationCode', sa.String(length=6), nullable=True))
    
    # Make email non-nullable again
    op.alter_column('users', 'email',
               existing_type=sa.String(length=255),
               nullable=False,
               existing_server_default=None)
               
    # Drop updatedAt column
    op.drop_column('users', 'updatedAt')
    
    # Drop firebaseUid column and index
    op.drop_index(op.f('ix_users_firebaseUid'), table_name='users')
    op.drop_column('users', 'firebaseUid')
