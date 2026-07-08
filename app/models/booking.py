import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum as SQLEnum, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
import enum

class BookingStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REQUESTED = "REQUESTED"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    PROVIDER_ACCEPTED = "PROVIDER_ACCEPTED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"

class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    providerId: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    serviceId: Mapped[str] = mapped_column(String(36), ForeignKey("services.id"), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(SQLEnum(BookingStatus), default=BookingStatus.REQUESTED, nullable=False)
    dateTime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    slot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    baseAmount: Mapped[float | None] = mapped_column(Float, nullable=True)
    gstAmount: Mapped[float | None] = mapped_column(Float, nullable=True)
    commissionAmount: Mapped[float | None] = mapped_column(Float, nullable=True)
    providerAmount: Mapped[float | None] = mapped_column(Float, nullable=True)
    durationMinutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    paymentMethod: Mapped[str] = mapped_column(String(50), default="COD", nullable=False)
    paymentStatus: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    isInstant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paymentId: Mapped[str | None] = mapped_column(String(255), nullable=True)
    orderId: Mapped[str | None] = mapped_column(String(255), nullable=True)
    holdExpiresAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    idempotencyKey: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('providerId', 'dateTime', name='uq_provider_datetime'),
    )

    # Relationships
    user = relationship("User", foreign_keys=[userId], back_populates="bookings")
    provider = relationship("User", foreign_keys=[providerId], back_populates="jobs")
    service = relationship("Service", back_populates="bookings")
    
    reviews = relationship("Review", back_populates="booking", cascade="all, delete-orphan")
    events = relationship("BookingEvent", back_populates="booking", cascade="all, delete-orphan")
    transactions = relationship("PaymentTransaction", back_populates="booking", cascade="all, delete-orphan")
    payoutRecord = relationship("PayoutRecord", uselist=False, back_populates="booking", cascade="all, delete-orphan")


class BookingEvent(Base):
    __tablename__ = "booking_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bookingId: Mapped[str] = mapped_column(String(36), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    fromStatus: Mapped[str] = mapped_column(String(50), nullable=False)
    toStatus: Mapped[str] = mapped_column(String(50), nullable=False)
    actorId: Mapped[str] = mapped_column(String(100), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    booking = relationship("Booking", back_populates="events")


class PayoutRecord(Base):
    __tablename__ = "payout_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    providerId: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    bookingId: Mapped[str] = mapped_column(String(36), ForeignKey("bookings.id"), unique=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False) # PENDING, PROCESSING, COMPLETED, FAILED
    
    # Snapshot of bank details at time of payout
    bankName: Mapped[str] = mapped_column(String(255), nullable=False)
    bankAccountName: Mapped[str] = mapped_column(String(255), nullable=False)
    bankAccountNumber: Mapped[str] = mapped_column(String(100), nullable=False)
    bankIFSC: Mapped[str] = mapped_column(String(50), nullable=False)
    
    transactionId: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    provider = relationship("User", back_populates="payoutRecords")
    booking = relationship("Booking", back_populates="payoutRecord")
