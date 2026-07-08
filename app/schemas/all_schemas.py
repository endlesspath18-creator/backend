from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.models.user import Role
from app.models.service import ServiceStatus
from app.models.booking import BookingStatus

# --- AUTH SCHEMAS ---

class UserRegister(BaseModel):
    fullName: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8,max_length=72)
    role: Role = Role.USER
    phone: Optional[str] = None
    businessName: Optional[str] = None
    bankAccountName: Optional[str] = None
    bankAccountNumber: Optional[str] = None
    bankIFSC: Optional[str] = None
    bankName: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class VerifyOtp(BaseModel):
    email: str
    otp: str

class RefreshTokenRequest(BaseModel):
    refreshToken: str

class ChangePassword(BaseModel):
    currentPassword: str
    newPassword: str = Field(..., min_length=6)

class UpdateProfile(BaseModel):
    fullName: Optional[str] = None
    phone: Optional[str] = None

class UpdateProviderProfile(BaseModel):
    businessName: Optional[str] = None
    bio: Optional[str] = None
    experienceYears: Optional[int] = None
    bankAccountName: Optional[str] = None
    bankAccountNumber: Optional[str] = None
    bankIFSC: Optional[str] = None
    bankName: Optional[str] = None


# --- SERVICE SCHEMAS ---

class ServiceCreate(BaseModel):
    title: str = Field(..., min_length=3)
    category: str
    description: str = Field(..., min_length=10)
    price: float = Field(..., gt=0)
    durationMinutes: int = Field(default=60, gt=0)
    images: Optional[List[str]] = Field(default_factory=list)

class ServiceUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    durationMinutes: Optional[int] = None
    images: Optional[List[str]] = None
    status: Optional[ServiceStatus] = None
    isActive: Optional[bool] = None


# --- BOOKING SCHEMAS ---

class BookingCreate(BaseModel):
    serviceId: str
    scheduledDate: str  # ISO8601 string
    slot: str
    address: str
    notes: Optional[str] = None
    paymentMethod: Optional[str] = "COD"
    idempotencyKey: Optional[str] = None

class ConfirmPaymentRequest(BaseModel):
    bookingId: str
    razorpayPaymentId: str
    razorpayOrderId: str
    razorpaySignature: str

class PaymentFailureRequest(BaseModel):
    bookingId: str
    reason: str

class RescheduleRequest(BaseModel):
    scheduledDate: str
    slot: str

class CancelRequest(BaseModel):
    reason: Optional[str] = None


# --- SUPPORT & OTHER SCHEMAS ---

class TicketCreate(BaseModel):
    subject: str
    description: str
    category: Optional[str] = None
    bookingId: Optional[str] = None

class ReviewCreate(BaseModel):
    bookingId: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class BannerCreate(BaseModel):
    imageUrl: str
    link: Optional[str] = None
    isActive: Optional[bool] = True

class FavoriteCreate(BaseModel):
    serviceId: Optional[str] = None
    providerId: Optional[str] = None

class PayoutConfigUpdate(BaseModel):
    upiId: Optional[str] = None
    accountName: Optional[str] = None
    bankName: Optional[str] = None
    accountNumber: Optional[str] = None
    ifscCode: Optional[str] = None
