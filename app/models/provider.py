import uuid
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class ProviderProfile(Base):
    __tablename__ = "provider_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    businessName: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    experienceYears: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    totalJobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    isOnline: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Banking Details
    bankAccountName: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bankAccountNumber: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bankIFSC: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bankName: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship
    user = relationship("User", back_populates="providerProfile")
