import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
import enum

class Role(str, enum.Enum):
    USER = "USER"
    PROVIDER = "PROVIDER"
    ADMIN = "ADMIN"

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fullName: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    passwordHash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[Role] = mapped_column(SQLEnum(Role), default=Role.USER, nullable=False)
    isRoleSet: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    googleId: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    isActive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    profileImage: Mapped[str | None] = mapped_column(String(500), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    hasPaidPublishingFee: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canPublishService: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    isVerified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    isEmailVerified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    isPhoneVerified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    firebaseUid: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)

    # Relationships
    providerProfile = relationship("ProviderProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan")
    refreshTokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    services = relationship("Service", back_populates="provider", cascade="all, delete-orphan")
    
    bookings = relationship("Booking", foreign_keys="[Booking.userId]", back_populates="user", cascade="all, delete-orphan")
    jobs = relationship("Booking", foreign_keys="[Booking.providerId]", back_populates="provider", cascade="all, delete-orphan")
    
    reviewsAsUser = relationship("Review", foreign_keys="[Review.userId]", back_populates="user", cascade="all, delete-orphan")
    reviewsAsProvider = relationship("Review", foreign_keys="[Review.providerId]", back_populates="provider", cascade="all, delete-orphan")
    
    payoutRecords = relationship("PayoutRecord", back_populates="provider")
    transactions = relationship("PaymentTransaction", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", foreign_keys="[Favorite.userId]", back_populates="user", cascade="all, delete-orphan")
    providerFavorites = relationship("Favorite", foreign_keys="[Favorite.providerId]", back_populates="provider", cascade="all, delete-orphan")
    supportTickets = relationship("SupportTicket", back_populates="user", cascade="all, delete-orphan")
