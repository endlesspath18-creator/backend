import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_

from app.database.session import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, verify_token
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.extra import RefreshToken
from app.schemas.all_schemas import UserRegister, UserLogin, VerifyOtp, RefreshTokenRequest, ChangePassword, UpdateProfile
from app.utils.response import success_response, error_response
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

async def generate_and_save_tokens(user_id: str, role: str, db: AsyncSession):
    access_token = create_access_token({"id": user_id, "role": role})
    refresh_token = create_refresh_token({"id": user_id, "role": role})
    
    # Refresh token rotation / management: delete old tokens if user has too many sessions (limit to 5)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.userId == user_id)
    )
    tokens = result.scalars().all()
    if len(tokens) >= 5:
        for t in tokens:
            await db.delete(t)
        await db.commit()

    db_token = RefreshToken(
        token=refresh_token,
        userId=user_id,
        expiresAt=datetime.utcnow() + timedelta(days=30)
    )
    db.add(db_token)
    await db.commit()
    return access_token, refresh_token


@router.post("/register")
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    email_normalized = payload.email.lower().strip()
    
    # Check uniqueness
    query = select(User).where(
        or_(
            User.email == email_normalized,
            *( [User.phone == payload.phone] if payload.phone else [] )
        )
    )
    result = await db.execute(query)
    existing_user = result.scalar_one_or_none()
    if existing_user:
        return error_response("User already exists with this email or phone number.", status_code=400)
    
    # Hash password
    pwd_hash = hash_password(payload.password)
    
    # OTP details
    otp = str(random.randint(100000, 999999))
    otp_expiry = datetime.utcnow() + timedelta(minutes=15)
    
    # Create user
    new_user = User(
        fullName=payload.fullName,
        email=email_normalized,
        phone=payload.phone,
        passwordHash=pwd_hash,
        role=payload.role,
        isActive=False, # Verify OTP first
        verificationCode=otp,
        otpExpiry=otp_expiry
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # Create provider profile if role is PROVIDER
    if payload.role == Role.PROVIDER:
        provider_profile = ProviderProfile(
            userId=new_user.id,
            businessName=payload.businessName or payload.fullName,
            bankAccountName=payload.bankAccountName,
            bankAccountNumber=payload.bankAccountNumber,
            bankIFSC=payload.bankIFSC,
            bankName=payload.bankName
        )
        db.add(provider_profile)
        await db.commit()
        
    print(f"[AUTH] OTP for {email_normalized}: {otp}")
    
    return success_response(
        "Registration successful. Please verify your account.",
        data={
            "userId": new_user.id,
            "email": new_user.email,
            "phone": new_user.phone,
            "debugOtp": otp
        },
        status_code=201
    )


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOtp, db: AsyncSession = Depends(get_db)):
    email_normalized = payload.email.lower().strip()
    result = await db.execute(
        select(User).where(User.email == email_normalized)
    )
    user = result.scalar_one_or_none()
    if not user:
        return error_response("User not found.", status_code=404)
        
    if user.isActive:
        return error_response("Account is already active.", status_code=400)
        
    if user.verificationCode != payload.otp:
        return error_response("Invalid verification code.", status_code=400)
        
    if user.otpExpiry and user.otpExpiry < datetime.utcnow():
        return error_response("Verification code has expired.", status_code=400)
        
    # Mark verified & active
    user.isActive = True
    user.isEmailVerified = True
    user.isPhoneVerified = True
    user.verificationCode = None
    user.otpExpiry = None
    db.add(user)
    await db.commit()
    
    # Create tokens
    access_token, refresh_token = await generate_and_save_tokens(user.id, user.role.value, db)
    
    return success_response(
        "Account verified successfully",
        data={
            "token": access_token,
            "refreshToken": refresh_token,
            "user": {
                "id": user.id,
                "fullName": user.fullName,
                "email": user.email,
                "role": user.role.value,
                "isRoleSet": user.isRoleSet
            }
        }
    )


@router.post("/login")
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    identifier = payload.email.lower().strip()
    
    result = await db.execute(
        select(User)
        .where(or_(User.email == identifier, User.phone == payload.email))
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return error_response("No account found with these credentials.", status_code=401)
        
    if not user.isActive:
        if user.verificationCode:
            return error_response("Account not verified. Please verify your email/phone.", status_code=403)
        return error_response("Your account is currently inactive. Please contact support.", status_code=403)
        
    if not user.passwordHash:
        return error_response("This account is linked with Google. Please login using Google.", status_code=401)
        
    if not verify_password(payload.password, user.passwordHash):
        return error_response("The password you entered is incorrect.", status_code=401)
        
    # Fetch provider profile if provider
    provider_dict = None
    if user.role == Role.PROVIDER:
        result_profile = await db.execute(
            select(ProviderProfile).where(ProviderProfile.userId == user.id)
        )
        profile = result_profile.scalar_one_or_none()
        if profile:
            provider_dict = {
                "id": profile.id,
                "userId": profile.userId,
                "businessName": profile.businessName,
                "bio": profile.bio,
                "experienceYears": profile.experienceYears,
                "rating": profile.rating,
                "totalJobs": profile.totalJobs,
                "isOnline": profile.isOnline,
                "bankName": profile.bankName,
                "bankAccountName": profile.bankAccountName,
                "bankAccountNumber": profile.bankAccountNumber,
                "bankIFSC": profile.bankIFSC
            }

    access_token, refresh_token = await generate_and_save_tokens(user.id, user.role.value, db)
    
    return success_response(
        "Login successful",
        data={
            "token": access_token,
            "refreshToken": refresh_token,
            "user": {
                "id": user.id,
                "fullName": user.fullName,
                "email": user.email,
                "role": user.role.value,
                "isRoleSet": user.isRoleSet,
                "hasPaidPublishingFee": user.hasPaidPublishingFee,
                "canPublishService": user.canPublishService,
                "providerProfile": provider_dict
            }
        }
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    provider_dict = None
    if current_user.role == Role.PROVIDER:
        result_profile = await db.execute(
            select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
        )
        profile = result_profile.scalar_one_or_none()
        if profile:
            provider_dict = {
                "id": profile.id,
                "userId": profile.userId,
                "businessName": profile.businessName,
                "bio": profile.bio,
                "experienceYears": profile.experienceYears,
                "rating": profile.rating,
                "totalJobs": profile.totalJobs,
                "isOnline": profile.isOnline,
                "bankName": profile.bankName,
                "bankAccountName": profile.bankAccountName,
                "bankAccountNumber": profile.bankAccountNumber,
                "bankIFSC": profile.bankIFSC
            }

    user_data = {
        "id": current_user.id,
        "fullName": current_user.fullName,
        "email": current_user.email,
        "phone": current_user.phone,
        "role": current_user.role.value,
        "isRoleSet": current_user.isRoleSet,
        "isActive": current_user.isActive,
        "hasPaidPublishingFee": current_user.hasPaidPublishingFee,
        "canPublishService": current_user.canPublishService,
        "createdAt": current_user.createdAt.isoformat(),
        "providerProfile": provider_dict
    }
    return success_response("User profile retrieved", data=user_data)


@router.patch("/profile")
async def update_profile(
    payload: UpdateProfile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if payload.fullName is not None:
        current_user.fullName = payload.fullName
    if payload.phone is not None:
        current_user.phone = payload.phone
        
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return success_response(
        "Profile updated successfully",
        data={
            "id": current_user.id,
            "fullName": current_user.fullName,
            "email": current_user.email,
            "phone": current_user.phone,
            "role": current_user.role.value
        }
    )


@router.patch("/password")
async def update_password(
    payload: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.passwordHash or not verify_password(payload.currentPassword, current_user.passwordHash):
        return error_response("Current password incorrect.", status_code=401)
        
    current_user.passwordHash = hash_password(payload.newPassword)
    db.add(current_user)
    await db.commit()
    
    return success_response("Password updated successfully.")


@router.post("/logout")
async def logout(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == payload.refreshToken)
    )
    token = result.scalar_one_or_none()
    if token:
        await db.delete(token)
        await db.commit()
    return success_response("Logged out successfully.")


@router.post("/refresh")
async def refresh(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    token_payload = verify_token(payload.refreshToken)
    if not token_payload:
        return error_response("Invalid refresh token", status_code=401)
        
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == payload.refreshToken)
    )
    stored_token = result.scalar_one_or_none()
    if not stored_token or stored_token.expiresAt < datetime.utcnow():
        if stored_token:
            await db.delete(stored_token)
            await db.commit()
        return error_response("Invalid or expired refresh token", status_code=401)
        
    access_token = create_access_token({"id": token_payload.get("id"), "role": token_payload.get("role")})
    return success_response("Token refreshed", data={"accessToken": access_token})
