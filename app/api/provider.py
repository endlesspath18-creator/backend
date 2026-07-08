from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.booking import Booking, BookingStatus
from app.schemas.all_schemas import UpdateProviderProfile
from app.utils.response import success_response, error_response
from app.api.deps import require_role, get_current_provider

router = APIRouter(prefix="/provider", tags=["Provider"])

@router.get("/dashboard")
async def get_provider_dashboard_stats(
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
    profile_res = await db.execute(profile_stmt)
    profile = profile_res.scalar_one_or_none()
    
    if not profile:
        return error_response("Provider profile not found", status_code=404)
        
    # Total Completed Earnings
    earnings_stmt = select(func.sum(Booking.amount)).where(
        Booking.providerId == current_user.id,
        Booking.status == BookingStatus.COMPLETED
    )
    earnings_res = await db.execute(earnings_stmt)
    total_earnings = earnings_res.scalar_one() or 0.0
    
    # Pending requests count
    pending_stmt = select(func.count(Booking.id)).where(
        Booking.providerId == current_user.id,
        Booking.status == BookingStatus.PENDING
    )
    pending_res = await db.execute(pending_stmt)
    pending_count = pending_res.scalar_one() or 0
    
    # Active jobs count
    active_stmt = select(func.count(Booking.id)).where(
        Booking.providerId == current_user.id,
        Booking.status.in_([BookingStatus.ACCEPTED, BookingStatus.IN_PROGRESS])
    )
    active_res = await db.execute(active_stmt)
    active_count = active_res.scalar_one() or 0
    
    requires_bank_update = not all([
        profile.bankAccountNumber,
        profile.bankIFSC,
        profile.bankName,
        profile.bankAccountName
    ])
    
    return success_response(
        "Dashboard stats fetched",
        data={
            "earnings": float(total_earnings),
            "completedJobs": profile.totalJobs,
            "pendingRequests": pending_count,
            "activeJobs": active_count,
            "rating": profile.rating,
            "isOnline": profile.isOnline,
            "requiresBankUpdate": requires_bank_update
        }
    )


@router.get("/requests")
async def get_incoming_requests(
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Booking)
        .where(Booking.providerId == current_user.id, Booking.status == BookingStatus.PENDING)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.service)
        )
        .order_by(Booking.createdAt.desc())
    )
    res = await db.execute(stmt)
    bookings = res.scalars().all()
    
    requests_list = []
    for b in bookings:
        requests_list.append({
            "id": b.id,
            "userId": b.userId,
            "providerId": b.providerId,
            "serviceId": b.serviceId,
            "status": b.status.value,
            "dateTime": b.dateTime.isoformat(),
            "slot": b.slot,
            "address": b.address,
            "notes": b.notes,
            "amount": b.amount,
            "paymentMethod": b.paymentMethod,
            "paymentStatus": b.paymentStatus,
            "createdAt": b.createdAt.isoformat(),
            "user": {
                "fullName": b.user.fullName,
                "phone": b.user.phone,
                "email": b.user.email
            } if b.user else None,
            "service": {
                "title": b.service.title,
                "category": b.service.category,
                "price": b.service.price
            } if b.service else None
        })
        
    return success_response("Incoming requests fetched", data=requests_list)


@router.get("/active-jobs")
async def get_active_jobs(
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Booking)
        .where(
            Booking.providerId == current_user.id,
            Booking.status.in_([BookingStatus.ACCEPTED, BookingStatus.IN_PROGRESS])
        )
        .options(
            selectinload(Booking.user),
            selectinload(Booking.service)
        )
        .order_by(Booking.dateTime.asc())
    )
    res = await db.execute(stmt)
    bookings = res.scalars().all()
    
    jobs_list = []
    for b in bookings:
        jobs_list.append({
            "id": b.id,
            "userId": b.userId,
            "providerId": b.providerId,
            "serviceId": b.serviceId,
            "status": b.status.value,
            "dateTime": b.dateTime.isoformat(),
            "slot": b.slot,
            "address": b.address,
            "notes": b.notes,
            "amount": b.amount,
            "paymentMethod": b.paymentMethod,
            "paymentStatus": b.paymentStatus,
            "createdAt": b.createdAt.isoformat(),
            "user": {
                "fullName": b.user.fullName,
                "phone": b.user.phone
            } if b.user else None,
            "service": {
                "title": b.service.title,
                "category": b.service.category
            } if b.service else None
        })
        
    return success_response("Active jobs fetched", data=jobs_list)


@router.patch("/profile")
async def update_provider_profile(
    payload: UpdateProviderProfile,
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
    profile_res = await db.execute(profile_stmt)
    profile = profile_res.scalar_one_or_none()
    
    if not profile:
        return error_response("Provider profile not found", status_code=404)
        
    # Update fields
    if payload.businessName is not None:
        profile.businessName = payload.businessName
    if payload.bio is not None:
        profile.bio = payload.bio
    if payload.experienceYears is not None:
        profile.experienceYears = payload.experienceYears
    if payload.bankAccountName is not None:
        profile.bankAccountName = payload.bankAccountName
    if payload.bankAccountNumber is not None:
        profile.bankAccountNumber = payload.bankAccountNumber
    if payload.bankIFSC is not None:
        profile.bankIFSC = payload.bankIFSC
    if payload.bankName is not None:
        profile.bankName = payload.bankName
        
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    
    profile_dict = {
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
    return success_response("Business profile updated successfully", data=profile_dict)


@router.patch("/availability")
async def toggle_availability(
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
    profile_res = await db.execute(profile_stmt)
    profile = profile_res.scalar_one_or_none()
    
    if not profile:
        return error_response("Provider profile not found", status_code=404)
        
    profile.isOnline = not profile.isOnline
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    
    status_str = "Online" if profile.isOnline else "Offline"
    
    profile_dict = {
        "id": profile.id,
        "userId": profile.userId,
        "businessName": profile.businessName,
        "isOnline": profile.isOnline
    }
    return success_response(f"You are now {status_str}", data=profile_dict)
