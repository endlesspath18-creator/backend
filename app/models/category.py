import uuid
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=True)
    image: Mapped[str] = mapped_column(String(500), nullable=True)
    icon: Mapped[str] = mapped_column(String(100), nullable=True)
    isActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
