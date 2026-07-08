from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.service import Service
from app.models.booking import Booking, BookingStatus, BookingEvent
from app.models.payment import PaymentTransaction
from app.models.extra import Favorite, RefreshToken, Notification, SupportTicket, Address
from app.schemas.all_schemas import TicketCreate, ReviewCreate, FavoriteCreate, ChangePassword
from app.utils.response import success_response, error_response
from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password
from datetime import datetime

router = APIRouter(prefix="/me", tags=["Me / Account"])

@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Upcoming bookings
    upcoming_stmt = (
        select(Booking)
        .where(
            Booking.userId == current_user.id,
            Booking.status.in_([BookingStatus.ACCEPTED, BookingStatus.PROVIDER_ACCEPTED, BookingStatus.CONFIRMED]),
            Booking.dateTime >= datetime.utcnow()
        )
        .options(
            selectinload(Booking.service),
            selectinload(Booking.provider)
        )
        .order_by(Booking.dateTime.asc())
        .limit(5)
    )
    upcoming_res = await db.execute(upcoming_stmt)
    upcoming_bookings = upcoming_res.scalars().all()

    # Counts
    total_bookings_stmt = select(func.count(Booking.id)).where(Booking.userId == current_user.id)
    total_bookings_res = await db.execute(total_bookings_stmt)
    total_bookings = total_bookings_res.scalar_one() or 0

    saved_prov_stmt = select(func.count(Favorite.id)).where(
        Favorite.userId == current_user.id,
        Favorite.providerId.isnot(None)
    )
    saved_prov_res = await db.execute(saved_prov_stmt)
    saved_providers = saved_prov_res.scalar_one() or 0

    # Recent activity
    activity_stmt = (
        select(BookingEvent)
        .join(Booking)
        .where(Booking.userId == current_user.id)
        .options(selectinload(BookingEvent.booking).selectinload(Booking.service))
        .order_by(BookingEvent.createdAt.desc())
        .limit(5)
    )
    activity_res = await db.execute(activity_stmt)
    recent_activity = activity_res.scalars().all()

    upcoming_list = []
    for b in upcoming_bookings:
        upcoming_list.append({
            "id": b.id,
            "dateTime": b.dateTime.isoformat(),
            "slot": b.slot,
            "address": b.address,
            "amount": b.amount,
            "status": b.status.value,
            "service": {"title": b.service.title} if b.service else None,
            "provider": {"fullName": b.provider.fullName} if b.provider else None
        })

    recent_activity_list = []
    for event in recent_activity:
        recent_activity_list.append({
            "id": event.id,
            "fromStatus": event.fromStatus,
            "toStatus": event.toStatus,
            "createdAt": event.createdAt.isoformat(),
            "booking": {
                "id": event.booking.id,
                "service": {"title": event.booking.service.title} if event.booking.service else None
            }
        })

    return success_response(
        "Dashboard data fetched",
        data={
            "upcomingBookings": upcoming_list,
            "stats": {
                "totalBookings": total_bookings,
                "activeBookings": len(upcoming_bookings),
                "savedProviders": saved_providers
            },
            "recentActivity": recent_activity_list
        }
    )


@router.get("/bookings")
async def get_my_bookings(
    status: str | None = None,
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    where_clause = [Booking.userId == current_user.id]
    if status:
        where_clause.append(Booking.status == status)

    stmt = (
        select(Booking)
        .where(and_(*where_clause))
        .options(
            selectinload(Booking.service),
            selectinload(Booking.provider),
            selectinload(Booking.reviews)
        )
        .order_by(Booking.dateTime.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    res = await db.execute(stmt)
    bookings = res.scalars().all()

    total_stmt = select(func.count(Booking.id)).where(and_(*where_clause))
    total_res = await db.execute(total_stmt)
    total = total_res.scalar_one() or 0

    bookings_list = []
    for b in bookings:
        bookings_list.append({
            "id": b.id,
            "status": b.status.value,
            "dateTime": b.dateTime.isoformat(),
            "slot": b.slot,
            "address": b.address,
            "amount": b.amount,
            "paymentMethod": b.paymentMethod,
            "paymentStatus": b.paymentStatus,
            "service": {"title": b.service.title, "images": b.service.images} if b.service else None,
            "provider": {"fullName": b.provider.fullName, "phone": b.provider.phone} if b.provider else None,
            "reviews": [{"id": r.id, "rating": r.rating, "comment": r.comment} for r in b.reviews]
        })

    return success_response(
        "My bookings fetched",
        data=bookings_list
    )


@router.get("/favorites")
async def get_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Favorite)
        .where(Favorite.userId == current_user.id)
        .options(
            selectinload(Favorite.service).selectinload(Service.provider),
            selectinload(Favorite.provider).selectinload(User.providerProfile)
        )
    )
    res = await db.execute(stmt)
    favorites = res.scalars().all()

    fav_list = []
    for f in favorites:
        service_dict = None
        if f.service:
            service_dict = {
                "id": f.service.id,
                "title": f.service.title,
                "price": f.service.price,
                "category": f.service.category,
                "images": f.service.images,
                "provider": {"fullName": f.service.provider.fullName} if f.service.provider else None
            }

        provider_dict = None
        if f.provider:
            provider_dict = {
                "id": f.provider.id,
                "fullName": f.provider.fullName,
                "providerProfile": {
                    "businessName": f.provider.providerProfile.businessName,
                    "rating": f.provider.providerProfile.rating
                } if f.provider.providerProfile else None
            }

        fav_list.append({
            "id": f.id,
            "userId": f.userId,
            "serviceId": f.serviceId,
            "providerId": f.providerId,
            "service": service_dict,
            "provider": provider_dict
        })

    return success_response("Favorites fetched", data=fav_list)


@router.post("/favorites")
async def add_favorite(
    payload: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    new_fav = Favorite(
        userId=current_user.id,
        serviceId=payload.serviceId,
        providerId=payload.providerId
    )
    db.add(new_fav)
    await db.commit()
    await db.refresh(new_fav)
    
    return success_response("Added to favorites", data={
        "id": new_fav.id,
        "userId": new_fav.userId,
        "serviceId": new_fav.serviceId,
        "providerId": new_fav.providerId
    }, status_code=201)


@router.delete("/favorites/{id}")
async def remove_favorite(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Favorite).where(Favorite.id == id, Favorite.userId == current_user.id)
    res = await db.execute(stmt)
    fav = res.scalar_one_or_none()

    if not fav:
        return error_response("Favorite not found", status_code=404)

    await db.delete(fav)
    await db.commit()
    return success_response("Removed from favorites")


@router.get("/payments")
async def get_payments_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(PaymentTransaction)
        .where(PaymentTransaction.userId == current_user.id)
        .options(
            selectinload(PaymentTransaction.booking).selectinload(Booking.service)
        )
        .order_by(PaymentTransaction.createdAt.desc())
    )
    res = await db.execute(stmt)
    transactions = res.scalars().all()

    tx_list = []
    for tx in transactions:
        tx_list.append({
            "id": tx.id,
            "type": tx.type,
            "amount": tx.amount,
            "status": tx.status,
            "paymentId": tx.paymentId,
            "orderId": tx.orderId,
            "createdAt": tx.createdAt.isoformat(),
            "booking": {
                "id": tx.booking.id,
                "amount": tx.booking.amount,
                "service": {"title": tx.booking.service.title} if tx.booking and tx.booking.service else None
            } if tx.booking else None
        })

    return success_response("Payments transactions history fetched", data=tx_list)


@router.get("/notifications")
async def get_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.userId == current_user.id).order_by(Notification.createdAt.desc())
    res = await db.execute(stmt)
    notifications = res.scalars().all()

    notifications_list = []
    for n in notifications:
        notifications_list.append({
            "id": n.id,
            "userId": n.userId,
            "title": n.title,
            "message": n.message,
            "isRead": n.isRead,
            "type": n.type,
            "meta": n.meta,
            "createdAt": n.createdAt.isoformat()
        })

    return success_response("Notifications fetched", data=notifications_list)


@router.patch("/notifications/{id}/read")
async def mark_notification_read(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.id == id, Notification.userId == current_user.id)
    res = await db.execute(stmt)
    notification = res.scalar_one_or_none()

    if not notification:
        return error_response("Notification not found", status_code=404)

    notification.isRead = True
    db.add(notification)
    await db.commit()

    return success_response("Marked as read")


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    provider_dict = None
    if current_user.role == Role.PROVIDER:
        result_profile = await db.execute(
            select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
        )
        profile = result_profile.scalar_one_or_none()
        if profile:
            provider_dict = {
                "id": profile.id,
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

    addresses_stmt = select(Address).where(Address.userId == current_user.id)
    addresses_res = await db.execute(addresses_stmt)
    addresses = addresses_res.scalars().all()

    profile_data = {
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
        "providerProfile": provider_dict,
        "addresses": [
            {
                "id": a.id,
                "label": a.label,
                "address": a.address,
                "city": a.city,
                "state": a.state,
                "zipCode": a.zipCode,
                "isDefault": a.isDefault
            }
            for a in addresses
        ]
    }
    return success_response("User profile retrieved", data=profile_data)


@router.patch("/profile")
async def update_profile(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if "fullName" in payload and payload["fullName"] is not None:
        current_user.fullName = payload["fullName"]
    if "phone" in payload and payload["phone"] is not None:
        current_user.phone = payload["phone"]
    if "profileImage" in payload and payload["profileImage"] is not None:
        current_user.profileImage = payload["profileImage"]
        
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return success_response("Profile updated successfully", data={
        "id": current_user.id,
        "fullName": current_user.fullName,
        "email": current_user.email,
        "phone": current_user.phone,
        "profileImage": current_user.profileImage
    })


@router.post("/change-password")
async def change_password(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    old_password = payload.get("oldPassword") or payload.get("currentPassword")
    new_password = payload.get("newPassword")
    
    if not old_password or not new_password:
        return error_response("Missing oldPassword or newPassword", status_code=400)
        
    if not current_user.passwordHash or not verify_password(old_password, current_user.passwordHash):
        return error_response("Invalid old password", status_code=400)
        
    current_user.passwordHash = hash_password(new_password)
    db.add(current_user)
    await db.commit()
    return success_response("Password changed successfully")


@router.post("/logout-all")
async def logout_all_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(RefreshToken).where(RefreshToken.userId == current_user.id)
    res = await db.execute(stmt)
    tokens = res.scalars().all()
    
    for t in tokens:
        await db.delete(t)
    await db.commit()
    return success_response("Logged out from all devices")


@router.post("/support/tickets")
async def create_support_ticket(
    payload: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    new_ticket = SupportTicket(
        userId=current_user.id,
        subject=payload.subject,
        description=payload.description,
        category=payload.category,
        bookingId=payload.bookingId,
        priority="MEDIUM",
        status="OPEN"
    )
    db.add(new_ticket)
    await db.commit()
    await db.refresh(new_ticket)
    
    return success_response("Support ticket created", data={
        "id": new_ticket.id,
        "userId": new_ticket.userId,
        "subject": new_ticket.subject,
        "description": new_ticket.description,
        "category": new_ticket.category,
        "bookingId": new_ticket.bookingId,
        "status": new_ticket.status,
        "priority": new_ticket.priority
    }, status_code=201)


@router.get("/support/tickets")
async def get_support_tickets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(SupportTicket).where(SupportTicket.userId == current_user.id).order_by(SupportTicket.createdAt.desc())
    res = await db.execute(stmt)
    tickets = res.scalars().all()
    
    tickets_list = []
    for t in tickets:
        tickets_list.append({
            "id": t.id,
            "userId": t.userId,
            "subject": t.subject,
            "description": t.description,
            "category": t.category,
            "bookingId": t.bookingId,
            "status": t.status,
            "priority": t.priority,
            "createdAt": t.createdAt.isoformat()
        })
        
    return success_response("Support tickets fetched", data=tickets_list)
