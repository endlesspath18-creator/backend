import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
import enum

class ServiceStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    DISABLED = "DISABLED"

class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    providerId: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    durationMinutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    status: Mapped[ServiceStatus] = mapped_column(SQLEnum(ServiceStatus), default=ServiceStatus.AVAILABLE, nullable=False)
    isActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    images: Mapped[list] = mapped_column(JSON, default=list, nullable=False) # Stores list of string URLs
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    totalJobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    provider = relationship("User", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    favorites = relationship("Favorite", back_populates="service", cascade="all, delete-orphan")
