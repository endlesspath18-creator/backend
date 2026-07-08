from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, and_

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.service import Service
from app.models.booking import Booking, BookingStatus
from app.models.payment import PaymentTransaction, AdminPaymentConfig
from app.models.extra import AuditLog, Banner
from app.schemas.all_schemas import PayoutConfigUpdate, BannerCreate
from app.utils.response import success_response, error_response
from app.api.deps import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
async def get_admin_dashboard_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # Total counts
    users_stmt = select(func.count(User.id)).where(User.role == Role.USER)
    users_res = await db.execute(users_stmt)
    users_count = users_res.scalar_one() or 0

    providers_stmt = select(func.count(User.id)).where(User.role == Role.PROVIDER)
    providers_res = await db.execute(providers_stmt)
    providers_count = providers_res.scalar_one() or 0

    bookings_stmt = select(func.count(Booking.id))
    bookings_res = await db.execute(bookings_stmt)
    bookings_count = bookings_res.scalar_one() or 0

    services_stmt = select(func.count(Service.id))
    services_res = await db.execute(services_stmt)
    services_count = services_res.scalar_one() or 0

    # Booking stats
    booking_stmt = (
        select(func.sum(PaymentTransaction.amount), func.sum(PaymentTransaction.commissionAmount))
        .where(PaymentTransaction.type == "BOOKING", PaymentTransaction.status == "SUCCESS")
    )
    booking_res = await db.execute(booking_stmt)
    booking_amount, booking_commission = booking_res.one()
    booking_amount = booking_amount or 0.0
    booking_commission = booking_commission or 0.0

    # Activation stats
    activation_stmt = (
        select(func.sum(PaymentTransaction.amount))
        .where(PaymentTransaction.type == "PROVIDER_ACTIVATION", PaymentTransaction.status == "SUCCESS")
    )
    activation_res = await db.execute(activation_stmt)
    activation_revenue = activation_res.scalar_one() or 0.0

    return success_response(
        "Admin stats fetched",
        data={
            "totalUsers": users_count,
            "totalProviders": providers_count,
            "totalBookings": bookings_count,
            "totalServices": services_count,
            "bookingRevenue": float(booking_amount),
            "bookingCommission": float(booking_commission),
            "activationRevenue": float(activation_revenue),
            "totalPlatformEarnings": float(booking_commission + activation_revenue)
        }
    )


@router.get("/finance/payout-settings")
async def get_payout_settings(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(AdminPaymentConfig)
    res = await db.execute(stmt)
    config = res.scalar_one_or_none()

    if not config:
        return success_response("Payout settings fetched", data={})

    # Mask sensitive details
    masked_acc = f"****{config.accountNumber[-4:]}" if config.accountNumber and len(config.accountNumber) >= 4 else "****"
    
    return success_response("Payout settings fetched", data={
        "id": config.id,
        "upiId": config.upiId,
        "accountName": config.accountName,
        "bankName": config.bankName,
        "accountNumber": masked_acc,
        "ifscCode": config.ifscCode
    })


@router.post("/finance/payout-settings")
async def update_payout_settings(
    payload: PayoutConfigUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    admin_email = "endlesspath18@gmail.com"
    if current_user.email != admin_email:
        print(f"SECURITY_ALERT: Unauthorized payout settings change attempt by {current_user.email}")
        return error_response("Access Denied: Only the primary admin can edit finance details.", status_code=403)

    stmt = select(AdminPaymentConfig)
    res = await db.execute(stmt)
    config = res.scalar_one_or_none()

    # Determine whether we update account number (skip if it's masked e.g. starting with **** or empty)
    account_num = payload.accountNumber
    should_update_acc = account_num and not account_num.startswith("****")

    if config:
        config.upiId = payload.upiId if payload.upiId is not None else config.upiId
        config.accountName = payload.accountName if payload.accountName is not None else config.accountName
        config.bankName = payload.bankName if payload.bankName is not None else config.bankName
        config.ifscCode = payload.ifscCode if payload.ifscCode is not None else config.ifscCode
        if should_update_acc:
            config.accountNumber = account_num
        db.add(config)
    else:
        config = AdminPaymentConfig(
            upiId=payload.upiId,
            accountName=payload.accountName,
            bankName=payload.bankName,
            accountNumber=account_num or "",
            ifscCode=payload.ifscCode
        )
        db.add(config)

    # Log action
    log = AuditLog(
        userId=current_user.id,
        action="UPDATE_PAYOUT_SETTINGS",
        details=f"Payout settings updated by {admin_email}. UPI: {payload.upiId}, Bank: {payload.bankName}",
        ipAddress=request.client.host if request.client else None
    )
    db.add(log)
    await db.commit()
    await db.refresh(config)

    return success_response("Payout settings updated and audited", data={
        "id": config.id,
        "upiId": config.upiId,
        "accountName": config.accountName,
        "bankName": config.bankName,
        "ifscCode": config.ifscCode
    })


@router.get("/finance/revenue-stats")
async def get_revenue_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # Group by type for SUCCESS transaction amounts
    stmt_types = (
        select(PaymentTransaction.type, func.sum(PaymentTransaction.amount))
        .where(PaymentTransaction.status == "SUCCESS")
        .group_by(PaymentTransaction.type)
    )
    res_types = await db.execute(stmt_types)
    type_stats = res_types.all()

    # Sum of PAID bookings amount
    paid_stmt = select(func.sum(Booking.amount)).where(Booking.paymentStatus == "PAID")
    paid_res = await db.execute(paid_stmt)
    paid_sum = paid_res.scalar_one() or 0.0

    # Structure data to match expected TS schema lists
    activation_revenue = 0.0
    booking_commission = 0.0
    booking_revenue = 0.0

    for row in type_stats:
        t, val = row
        val = float(val or 0)
        if t == "PROVIDER_ACTIVATION":
            activation_revenue = val
        elif t == "BOOKING":
            booking_revenue = val
            booking_commission = val / 1.18 * 0.10 # 10% commission on base

    result_data = {
        "activationRevenue": activation_revenue,
        "bookingCommission": booking_commission,
        "bookingRevenue": booking_revenue,
        "totalPlatformEarnings": booking_commission + activation_revenue
    }

    return success_response("Revenue stats fetched", data=result_data)


@router.get("/finance/transactions")
async def get_all_transactions(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(PaymentTransaction)
        .options(selectinload(PaymentTransaction.user))
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
            "user": {"fullName": tx.user.fullName, "email": tx.user.email} if tx.user else None
        })

    return success_response("Transactions fetched", data=tx_list)


@router.get("/users")
async def get_all_users(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.role == Role.USER).order_by(User.createdAt.desc())
    res = await db.execute(stmt)
    users = res.scalars().all()

    users_list = []
    for u in users:
        users_list.append({
            "id": u.id,
            "fullName": u.fullName,
            "email": u.email,
            "phone": u.phone,
            "role": u.role.value,
            "isActive": u.isActive,
            "createdAt": u.createdAt.isoformat()
        })

    return success_response("Users fetched", data=users_list)


@router.get("/providers")
async def get_all_providers(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.role == Role.PROVIDER).options(selectinload(User.providerProfile)).order_by(User.createdAt.desc())
    res = await db.execute(stmt)
    providers = res.scalars().all()

    providers_list = []
    for p in providers:
        profile_dict = None
        if p.providerProfile:
            profile_dict = {
                "id": p.providerProfile.id,
                "businessName": p.providerProfile.businessName,
                "bio": p.providerProfile.bio,
                "experienceYears": p.providerProfile.experienceYears,
                "rating": p.providerProfile.rating,
                "totalJobs": p.providerProfile.totalJobs,
                "isOnline": p.providerProfile.isOnline,
                "bankName": p.providerProfile.bankName,
                "bankAccountName": p.providerProfile.bankAccountName,
                "bankAccountNumber": p.providerProfile.bankAccountNumber,
                "bankIFSC": p.providerProfile.bankIFSC
            }
        providers_list.append({
            "id": p.id,
            "fullName": p.fullName,
            "email": p.email,
            "phone": p.phone,
            "role": p.role.value,
            "isActive": p.isActive,
            "isVerified": p.isVerified,
            "hasPaidPublishingFee": p.hasPaidPublishingFee,
            "canPublishService": p.canPublishService,
            "createdAt": p.createdAt.isoformat(),
            "providerProfile": profile_dict
        })

    return success_response("Providers fetched", data=providers_list)


@router.patch("/users/{id}/toggle-status")
async def toggle_user_status(
    id: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.id == id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        return error_response("User not found", status_code=404)

    user.isActive = not user.isActive
    db.add(user)
    await db.commit()
    await db.refresh(user)

    status_str = "activated" if user.isActive else "deactivated"
    return success_response(f"User {status_str}", data={
        "id": user.id,
        "fullName": user.fullName,
        "isActive": user.isActive
    })


@router.get("/bookings")
async def get_all_bookings(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Booking)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.provider),
            selectinload(Booking.service)
        )
        .order_by(Booking.createdAt.desc())
    )
    res = await db.execute(stmt)
    bookings = res.scalars().all()

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
            "createdAt": b.createdAt.isoformat(),
            "user": {"fullName": b.user.fullName, "email": b.user.email} if b.user else None,
            "provider": {"fullName": b.provider.fullName} if b.provider else None,
            "service": {"title": b.service.title} if b.service else None
        })

    return success_response("Bookings fetched", data=bookings_list)


@router.patch("/providers/{id}/verify")
async def verify_provider(
    id: str,
    payload: dict,
    request: Request,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    is_verified = payload.get("isVerified", False)
    stmt = select(User).where(User.id == id)
    res = await db.execute(stmt)
    provider = res.scalar_one_or_none()

    if not provider:
        return error_response("Provider not found", status_code=404)

    provider.isVerified = is_verified
    db.add(provider)

    # Log action
    log = AuditLog(
        userId=current_user.id,
        action="VERIFY_PROVIDER" if is_verified else "UNVERIFY_PROVIDER",
        details=f"Provider {id} verification set to {is_verified} by admin ID: {current_user.id}",
        ipAddress=request.client.host if request.client else None
    )
    db.add(log)
    await db.commit()

    return success_response(f"Provider {'verified' if is_verified else 'unverified'} successfully")


@router.post("/providers/{id}/manual-unlock")
async def manual_unlock_provider(
    id: str,
    request: Request,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.id == id)
    res = await db.execute(stmt)
    provider = res.scalar_one_or_none()

    if not provider:
        return error_response("Provider not found", status_code=404)

    provider.hasPaidPublishingFee = True
    provider.canPublishService = True
    db.add(provider)

    # Log action
    log = AuditLog(
        userId=current_user.id,
        action="MANUAL_UNLOCK_PROVIDER",
        details=f"Provider {id} manually unlocked by admin ID: {current_user.id}",
        ipAddress=request.client.host if request.client else None
    )
    db.add(log)
    await db.commit()

    return success_response("Provider manually unlocked for publishing")


# --- Banner CRUD ---

@router.get("/banners")
async def get_banners(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Banner).order_by(Banner.createdAt.desc())
    res = await db.execute(stmt)
    banners = res.scalars().all()
    
    banners_list = []
    for b in banners:
        banners_list.append({
            "id": b.id,
            "imageUrl": b.imageUrl,
            "link": b.link,
            "isActive": b.isActive,
            "createdAt": b.createdAt.isoformat()
        })
    return success_response("Banners fetched", data=banners_list)


@router.post("/banners")
async def create_banner(
    payload: BannerCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    new_banner = Banner(
        imageUrl=payload.imageUrl,
        link=payload.link,
        isActive=payload.isActive
    )
    db.add(new_banner)
    await db.commit()
    await db.refresh(new_banner)
    
    return success_response("Banner created", data={
        "id": new_banner.id,
        "imageUrl": new_banner.imageUrl,
        "link": new_banner.link,
        "isActive": new_banner.isActive,
        "createdAt": new_banner.createdAt.isoformat()
    }, status_code=201)


@router.delete("/banners/{id}")
async def delete_banner(
    id: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Banner).where(Banner.id == id)
    res = await db.execute(stmt)
    banner = res.scalar_one_or_none()

    if not banner:
        return error_response("Banner not found", status_code=404)

    await db.delete(banner)
    await db.commit()
    return success_response("Banner deleted")
