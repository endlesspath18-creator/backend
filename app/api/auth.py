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
from app.schemas.all_schemas import UserRegister, UserLogin, FirebaseLoginRequest, RefreshTokenRequest, ChangePassword, UpdateProfile
from app.utils.response import success_response, error_response
from app.core.firebase import verify_firebase_token
from fastapi.responses import JSONResponse
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


@router.post("/firebase-login")
async def firebase_login(payload: FirebaseLoginRequest, db: AsyncSession = Depends(get_db)):
    # 1. Verify Firebase ID Token
    decoded_token = verify_firebase_token(payload.idToken)
    
    # 2. Extract Claims
    uid = decoded_token.get("uid")
    phone_number = decoded_token.get("phone_number") or payload.phone
    email = decoded_token.get("email")
    name = decoded_token.get("name") or (email.split("@")[0] if email else "Firebase User")
    picture = decoded_token.get("picture")
    
    if not uid:
        return error_response("Invalid Firebase token: missing uid claim.", status_code=400)
        
    firebase_info = decoded_token.get("firebase", {})
    sign_in_provider = firebase_info.get("sign_in_provider")
    
    if sign_in_provider == "phone" and not phone_number:
        return error_response("Authentication failed: phone number is missing from token.", status_code=400)
    elif sign_in_provider != "phone" and not email:
        return error_response("Authentication failed: email is missing from token.", status_code=400)
    elif not phone_number and not email:
        return error_response("Authentication failed: token must contain phone number or email.", status_code=400)
        
    # 3. Search database for user by firebaseUid
    query = select(User).where(User.firebaseUid == uid)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        # Search by phone or email to link existing accounts
        conditions = []
        if phone_number:
            conditions.append(User.phone == phone_number)
        if email:
            conditions.append(User.email == email.lower().strip())
            
        if conditions:
            query_exist = select(User).where(or_(*conditions))
            result_exist = await db.execute(query_exist)
            user = result_exist.scalar_one_or_none()
            
            if user:
                # Link existing user account
                user.firebaseUid = uid
                if phone_number:
                    user.phone = phone_number
                    user.isPhoneVerified = True
                if email:
                    user.email = email.lower().strip()
                    user.isEmailVerified = True
                if picture and not user.profileImage:
                    user.profileImage = picture
                user.isActive = True
                db.add(user)
                await db.commit()
                await db.refresh(user)
                print(f"[AUTH] Linked existing user {user.id} to firebaseUid {uid}")
                
    if not user:
        # Create a new user
        user_name = payload.fullName or name or (phone_number if phone_number else "New User")
        user_role = payload.role or Role.USER
        user_email = email.lower().strip() if email else None
        
        # Verify uniqueness of email or phone in database if present
        uniqueness_checks = []
        if user_email:
            uniqueness_checks.append(User.email == user_email)
        if phone_number:
            uniqueness_checks.append(User.phone == phone_number)
            
        if uniqueness_checks:
            query_unique = select(User).where(or_(*uniqueness_checks))
            result_unique = await db.execute(query_unique)
            clashing_user = result_unique.scalar_one_or_none()
            if clashing_user:
                if not clashing_user.firebaseUid:
                    clashing_user.firebaseUid = uid
                    if phone_number:
                        clashing_user.phone = phone_number
                        clashing_user.isPhoneVerified = True
                    if user_email:
                        clashing_user.email = user_email
                        clashing_user.isEmailVerified = True
                    clashing_user.isActive = True
                    db.add(clashing_user)
                    await db.commit()
                    await db.refresh(clashing_user)
                    user = clashing_user
                else:
                    return error_response("An account with this phone or email already exists.", status_code=400)
        
        if not user:
            new_user = User(
                firebaseUid=uid,
                fullName=user_name,
                email=user_email,
                phone=phone_number,
                role=user_role,
                isActive=True,
                isPhoneVerified=True if phone_number else False,
                isEmailVerified=True if email else False,
                profileImage=picture
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            user = new_user
            print(f"[AUTH] Created new user {user.id} with firebaseUid {uid}")
            
            # Create provider profile if role is PROVIDER
            if user_role == Role.PROVIDER:
                provider_profile = ProviderProfile(
                    userId=user.id,
                    businessName=payload.businessName or user_name,
                    bankAccountName=payload.bankAccountName,
                    bankAccountNumber=payload.bankAccountNumber,
                    bankIFSC=payload.bankIFSC,
                    bankName=payload.bankName
                )
                db.add(provider_profile)
                await db.commit()

    # 4. Generate backend access and refresh tokens
    access_token, refresh_token = await generate_and_save_tokens(user.id, user.role.value, db)
    
    # 5. Fetch provider profile details if applicable
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

    # 6. Format response
    user_data = {
        "id": user.id,
        "fullName": user.fullName,
        "email": user.email or "",
        "phone": user.phone or "",
        "role": user.role.value,
        "isRoleSet": user.isRoleSet,
        "hasPaidPublishingFee": user.hasPaidPublishingFee,
        "canPublishService": user.canPublishService,
        "profileImage": user.profileImage,
        "providerProfile": provider_dict
    }
    
    return JSONResponse(
        content={
            "success": True,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": user_data
        },
        status_code=200
    )




@router.post("/register")
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    email_clean = payload.email.lower().strip()
    
    # 1. Uniqueness check
    conditions = [User.email == email_clean]
    if payload.phone:
        conditions.append(User.phone == payload.phone.strip())
        
    query_exist = select(User).where(or_(*conditions))
    result_exist = await db.execute(query_exist)
    existing_user = result_exist.scalar_one_or_none()
    
    if existing_user:
        return error_response("An account with this email or phone number already exists.", status_code=400)
        
    # 2. Create the user
    new_user = User(
        fullName=payload.fullName,
        email=email_clean,
        phone=payload.phone.strip() if payload.phone else None,
        passwordHash=hash_password(payload.password),
        role=payload.role,
        isActive=True,
        isEmailVerified=True,
        isPhoneVerified=True if payload.phone else False
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # 3. Create provider profile if role is PROVIDER
    provider_dict = None
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
        await db.refresh(provider_profile)
        
        provider_dict = {
            "id": provider_profile.id,
            "userId": provider_profile.userId,
            "businessName": provider_profile.businessName,
            "bio": provider_profile.bio,
            "experienceYears": provider_profile.experienceYears,
            "rating": provider_profile.rating,
            "totalJobs": provider_profile.totalJobs,
            "isOnline": provider_profile.isOnline,
            "bankName": provider_profile.bankName,
            "bankAccountName": provider_profile.bankAccountName,
            "bankAccountNumber": provider_profile.bankAccountNumber,
            "bankIFSC": provider_profile.bankIFSC
        }
        
    # 4. Generate tokens
    access_token, refresh_token = await generate_and_save_tokens(new_user.id, new_user.role.value, db)
    
    user_data = {
        "id": new_user.id,
        "fullName": new_user.fullName,
        "email": new_user.email,
        "phone": new_user.phone or "",
        "role": new_user.role.value,
        "isRoleSet": new_user.isRoleSet,
        "hasPaidPublishingFee": new_user.hasPaidPublishingFee,
        "canPublishService": new_user.canPublishService,
        "profileImage": new_user.profileImage,
        "providerProfile": provider_dict
    }
    
    return JSONResponse(
        content={
            "success": True,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": user_data
        },
        status_code=201
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
