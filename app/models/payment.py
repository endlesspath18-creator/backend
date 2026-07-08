import uuid
from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False) # e.g. "BOOKING", "PROVIDER_ACTIVATION"
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    gstAmount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    commissionAmount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    providerAmount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False) # e.g. "PENDING", "SUCCESS", "FAILED"
    paymentId: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    orderId: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    gatewayResponse: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bookingId: Mapped[str | None] = mapped_column(String(36), ForeignKey("bookings.id"), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="transactions")
    booking = relationship("Booking", back_populates="transactions")


class AdminPaymentConfig(Base):
    __tablename__ = "admin_payment_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upiId: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accountName: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bankName: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accountNumber: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ifscCode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
