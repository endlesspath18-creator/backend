"""initial migration

Revision ID: 0001
Revises: None
Create Date: 2026-07-08 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('fullName', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('passwordHash', sa.String(length=255), nullable=True),
        sa.Column('role', sa.Enum('USER', 'PROVIDER', 'ADMIN', name='role'), nullable=False),
        sa.Column('isRoleSet', sa.Boolean(), nullable=False),
        sa.Column('googleId', sa.String(length=255), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=False),
        sa.Column('profileImage', sa.String(length=500), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('hasPaidPublishingFee', sa.Boolean(), nullable=False),
        sa.Column('canPublishService', sa.Boolean(), nullable=False),
        sa.Column('isVerified', sa.Boolean(), nullable=False),
        sa.Column('isEmailVerified', sa.Boolean(), nullable=False),
        sa.Column('isPhoneVerified', sa.Boolean(), nullable=False),
        sa.Column('verificationCode', sa.String(length=6), nullable=True),
        sa.Column('otpExpiry', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('phone'),
        sa.UniqueConstraint('googleId')
    )

    # 2. provider_profiles table
    op.create_table(
        'provider_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('businessName', sa.String(length=255), nullable=False),
        sa.Column('bio', sa.String(length=1000), nullable=True),
        sa.Column('experienceYears', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=False),
        sa.Column('totalJobs', sa.Integer(), nullable=False),
        sa.Column('isOnline', sa.Boolean(), nullable=False),
        sa.Column('bankAccountName', sa.String(length=255), nullable=True),
        sa.Column('bankAccountNumber', sa.String(length=100), nullable=True),
        sa.Column('bankIFSC', sa.String(length=50), nullable=True),
        sa.Column('bankName', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('userId')
    )

    # 3. services table
    op.create_table(
        'services',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('providerId', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=2000), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('durationMinutes', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('AVAILABLE', 'BUSY', 'DISABLED', name='servicestatus'), nullable=False),
        sa.Column('isActive', sa.Boolean(), nullable=False),
        sa.Column('images', sa.JSON(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=False),
        sa.Column('totalJobs', sa.Integer(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['providerId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. bookings table
    op.create_table(
        'bookings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('providerId', sa.String(length=36), nullable=False),
        sa.Column('serviceId', sa.String(length=36), nullable=False),
        sa.Column('status', sa.Enum('DRAFT', 'REQUESTED', 'PENDING', 'ACCEPTED', 'PROVIDER_ACCEPTED', 'PAYMENT_PENDING', 'CONFIRMED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'REJECTED', 'PAYMENT_FAILED', 'EXPIRED', 'REFUNDED', name='bookingstatus'), nullable=False),
        sa.Column('dateTime', sa.DateTime(), nullable=False),
        sa.Column('slot', sa.String(length=100), nullable=True),
        sa.Column('address', sa.String(length=500), nullable=False),
        sa.Column('notes', sa.String(length=1000), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('baseAmount', sa.Float(), nullable=True),
        sa.Column('gstAmount', sa.Float(), nullable=True),
        sa.Column('commissionAmount', sa.Float(), nullable=True),
        sa.Column('providerAmount', sa.Float(), nullable=True),
        sa.Column('durationMinutes', sa.Integer(), nullable=False),
        sa.Column('paymentMethod', sa.String(length=50), nullable=False),
        sa.Column('paymentStatus', sa.String(length=50), nullable=False),
        sa.Column('paymentId', sa.String(length=255), nullable=True),
        sa.Column('orderId', sa.String(length=255), nullable=True),
        sa.Column('holdExpiresAt', sa.DateTime(), nullable=True),
        sa.Column('idempotencyKey', sa.String(length=255), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['providerId'], ['users.id']),
        sa.ForeignKeyConstraint(['serviceId'], ['services.id']),
        sa.ForeignKeyConstraint(['userId'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotencyKey'),
        sa.UniqueConstraint('providerId', 'dateTime', name='uq_provider_datetime')
    )

    # 5. booking_events table
    op.create_table(
        'booking_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('bookingId', sa.String(length=36), nullable=False),
        sa.Column('fromStatus', sa.String(length=50), nullable=False),
        sa.Column('toStatus', sa.String(length=50), nullable=False),
        sa.Column('actorId', sa.String(length=100), nullable=False),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bookingId'], ['bookings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. payout_records table
    op.create_table(
        'payout_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('providerId', sa.String(length=36), nullable=False),
        sa.Column('bookingId', sa.String(length=36), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('bankName', sa.String(length=255), nullable=False),
        sa.Column('bankAccountName', sa.String(length=255), nullable=False),
        sa.Column('bankAccountNumber', sa.String(length=100), nullable=False),
        sa.Column('bankIFSC', sa.String(length=50), nullable=False),
        sa.Column('transactionId', sa.String(length=255), nullable=True),
        sa.Column('processedAt', sa.DateTime(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bookingId'], ['bookings.id']),
        sa.ForeignKeyConstraint(['providerId'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bookingId')
    )

    # 7. payment_transactions table
    op.create_table(
        'payment_transactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('gstAmount', sa.Float(), nullable=False),
        sa.Column('commissionAmount', sa.Float(), nullable=False),
        sa.Column('providerAmount', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('paymentId', sa.String(length=255), nullable=True),
        sa.Column('orderId', sa.String(length=255), nullable=True),
        sa.Column('gatewayResponse', sa.JSON(), nullable=True),
        sa.Column('bookingId', sa.String(length=36), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bookingId'], ['bookings.id']),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paymentId'),
        sa.UniqueConstraint('orderId')
    )

    # 8. admin_payment_configs table
    op.create_table(
        'admin_payment_configs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('upiId', sa.String(length=255), nullable=True),
        sa.Column('accountName', sa.String(length=255), nullable=True),
        sa.Column('bankName', sa.String(length=255), nullable=True),
        sa.Column('accountNumber', sa.String(length=100), nullable=True),
        sa.Column('ifscCode', sa.String(length=50), nullable=True),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 9. addresses table
    op.create_table(
        'addresses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('address', sa.String(length=500), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('state', sa.String(length=100), nullable=False),
        sa.Column('zipCode', sa.String(length=20), nullable=False),
        sa.Column('isDefault', sa.Boolean(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 10. favorites table
    op.create_table(
        'favorites',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('serviceId', sa.String(length=36), nullable=True),
        sa.Column('providerId', sa.String(length=36), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['providerId'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['serviceId'], ['services.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('userId', 'serviceId', name='uq_user_service'),
        sa.UniqueConstraint('userId', 'providerId', name='uq_user_provider')
    )

    # 11. support_tickets table
    op.create_table(
        'support_tickets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('bookingId', sa.String(length=100), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 12. refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('token', sa.String(length=500), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('expiresAt', sa.DateTime(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )

    # 13. notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.String(length=1000), nullable=False),
        sa.Column('isRead', sa.Boolean(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 14. reviews table
    op.create_table(
        'reviews',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('bookingId', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('providerId', sa.String(length=36), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.String(length=1000), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bookingId'], ['bookings.id']),
        sa.ForeignKeyConstraint(['providerId'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['userId'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bookingId')
    )

    # 15. banners table
    op.create_table(
        'banners',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('imageUrl', sa.String(length=500), nullable=False),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=False),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 16. audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('userId', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ipAddress', sa.String(length=50), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('banners')
    op.drop_table('reviews')
    op.drop_table('notifications')
    op.drop_table('refresh_tokens')
    op.drop_table('support_tickets')
    op.drop_table('favorites')
    op.drop_table('addresses')
    op.drop_table('admin_payment_configs')
    op.drop_table('payment_transactions')
    op.drop_table('payout_records')
    op.drop_table('booking_events')
    op.drop_table('bookings')
    op.drop_table('services')
    op.drop_table('provider_profiles')
    op.drop_table('users')
