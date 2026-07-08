import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, and_, func

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.service import Service, ServiceStatus
from app.models.booking import Booking, BookingStatus, BookingEvent, PayoutRecord
from app.models.payment import PaymentTransaction, AdminPaymentConfig
from app.models.extra import Notification, Review
from app.schemas.all_schemas import BookingCreate, ConfirmPaymentRequest, PaymentFailureRequest, RescheduleRequest, CancelRequest
from app.utils.response import success_response, error_response
from app.utils.razorpay import create_razorpay_order, verify_razorpay_signature, verify_webhook_signature
from app.api.deps import get_current_user, require_role, get_current_provider, get_current_admin
from app.core.config import settings

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post("")
async def create_booking(
    payload: BookingCreate,
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    # Check idempotency
    if payload.idempotencyKey:
        stmt = select(Booking).where(Booking.idempotencyKey == payload.idempotencyKey)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return success_response("Booking already exists", data=existing)

    # Fetch service & provider details
    service_stmt = select(Service).where(Service.id == payload.serviceId).options(selectinload(Service.provider))
    service_res = await db.execute(service_stmt)
    service = service_res.scalar_one_or_none()

    if not service:
        return error_response("Service not found", status_code=404)
    if not service.isActive:
        return error_response("This service is currently disabled", status_code=400)

    requested_start = datetime.fromisoformat(payload.scheduledDate.replace('Z', '+00:00')).replace(tzinfo=None)
    requested_end = requested_start + timedelta(minutes=service.durationMinutes)

    # Overlap check
    overlap_stmt = select(Booking).where(
        Booking.providerId == service.providerId,
        Booking.status.notin_([BookingStatus.CANCELLED, BookingStatus.REJECTED]),
        Booking.dateTime >= requested_start - timedelta(days=1),
        Booking.dateTime <= requested_start + timedelta(days=1)
    )
    overlap_res = await db.execute(overlap_stmt)
    potential_overlaps = overlap_res.scalars().all()

    for b in potential_overlaps:
        b_start = b.dateTime
        b_end = b_start + timedelta(minutes=b.durationMinutes)
        if requested_start < b_end and requested_end > b_start:
            return error_response("Provider is already booked for this time slot", status_code=409)

    method = "COD" if payload.paymentMethod == "COD" else "ONLINE"
    initial_status = BookingStatus.REQUESTED if method == "COD" else BookingStatus.PAYMENT_PENDING
    hold_expiry = datetime.utcnow() + timedelta(minutes=15) if method == "ONLINE" else None

    # Pricing Split Calculations (18% GST and 10% admin commission on base)
    total_amount = service.price
    base_amount = total_amount / 1.18
    gst_amount = total_amount - base_amount
    commission_amount = base_amount * 0.10
    provider_amount = base_amount - commission_amount

    # Create Booking record
    new_booking = Booking(
        userId=current_user.id,
        providerId=service.providerId,
        serviceId=service.id,
        status=initial_status,
        dateTime=requested_start,
        slot=payload.slot,
        address=payload.address,
        notes=payload.notes,
        amount=total_amount,
        baseAmount=base_amount,
        gstAmount=gst_amount,
        commissionAmount=commission_amount,
        providerAmount=provider_amount,
        durationMinutes=service.durationMinutes,
        paymentMethod=method,
        paymentStatus="PENDING",
        isInstant=payload.isInstant,
        holdExpiresAt=hold_expiry,
        idempotencyKey=payload.idempotencyKey
    )

    db.add(new_booking)
    await db.commit()
    await db.refresh(new_booking)

    # Razorpay Order creation if ONLINE
    razorpay_order = None
    if method == "ONLINE":
        try:
            razorpay_order = create_razorpay_order(total_amount, new_booking.id)
            new_booking.orderId = razorpay_order["id"]
            db.add(new_booking)
            await db.commit()
        except Exception:
            return error_response("Failed to connect to payment gateway. Please verify configuration.", status_code=502)

    # Create BookingEvent log
    event = BookingEvent(
        bookingId=new_booking.id,
        fromStatus="DRAFT",
        toStatus=initial_status.value,
        actorId=current_user.id,
        meta={"razorpayOrderId": razorpay_order["id"]} if razorpay_order else {"method": "COD"}
    )
    db.add(event)
    await db.commit()

    success_msg = "Booking initiated. Complete payment to confirm." if method == "ONLINE" else "Booking requested successfully."
    result_data = {
        "booking": {
            "id": new_booking.id,
            "userId": new_booking.userId,
            "providerId": new_booking.providerId,
            "serviceId": new_booking.serviceId,
            "status": new_booking.status.value,
            "dateTime": new_booking.dateTime.isoformat(),
            "slot": new_booking.slot,
            "address": new_booking.address,
            "notes": new_booking.notes,
            "amount": new_booking.amount,
            "paymentMethod": new_booking.paymentMethod,
            "paymentStatus": new_booking.paymentStatus,
            "orderId": new_booking.orderId
        },
        "razorpayOrder": razorpay_order,
        "key": settings.RAZORPAY_KEY_ID if razorpay_order else None
    }
    return success_response(success_msg, data=result_data, status_code=201)


@router.post("/confirm-payment")
async def confirm_payment(
    payload: ConfirmPaymentRequest,
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == payload.bookingId)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.userId != current_user.id:
        return error_response("Not authorized to confirm this booking", status_code=401)

    if booking.status == BookingStatus.CONFIRMED:
        return success_response("Booking already confirmed", data=booking)

    if booking.orderId != payload.razorpayOrderId:
        return error_response("Payment order ID does not match booking records", status_code=400)

    # Signature verification
    is_valid = verify_razorpay_signature(payload.razorpayOrderId, payload.razorpayPaymentId, payload.razorpaySignature)
    if not is_valid:
        return error_response("Invalid payment signature.", status_code=400)

    # Prevent replay attack
    tx_check = select(PaymentTransaction).where(PaymentTransaction.paymentId == payload.razorpayPaymentId)
    tx_res = await db.execute(tx_check)
    if tx_res.scalar_one_or_none():
        return success_response("Payment already processed", data=booking)

    # Update Booking & Create PaymentTransaction
    booking.status = BookingStatus.CONFIRMED
    booking.paymentStatus = "PAID"
    booking.paymentId = payload.razorpayPaymentId
    booking.holdExpiresAt = None
    db.add(booking)

    # Create PaymentTransaction record
    transaction = PaymentTransaction(
        userId=current_user.id,
        type="BOOKING",
        amount=booking.amount,
        gstAmount=booking.gstAmount or 0.0,
        commissionAmount=booking.commissionAmount or 0.0,
        providerAmount=booking.providerAmount or 0.0,
        status="SUCCESS",
        paymentId=payload.razorpayPaymentId,
        orderId=payload.razorpayOrderId,
        gatewayResponse=payload.model_dump(),
        bookingId=booking.id
    )
    db.add(transaction)

    # Create PayoutRecord using provider bank details snapshot
    p_profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == booking.providerId)
    p_profile_res = await db.execute(p_profile_stmt)
    p_profile = p_profile_res.scalar_one_or_none()

    if p_profile:
        payout = PayoutRecord(
            providerId=booking.providerId,
            bookingId=booking.id,
            amount=booking.providerAmount or 0.0,
            status="PENDING",
            bankName=p_profile.bankName or "Unknown",
            bankAccountName=p_profile.bankAccountName or "Unknown",
            bankAccountNumber=p_profile.bankAccountNumber or "Unknown",
            bankIFSC=p_profile.bankIFSC or "Unknown"
        )
        db.add(payout)

    # Log Event
    event = BookingEvent(
        bookingId=booking.id,
        fromStatus="PAYMENT_PENDING",
        toStatus="CONFIRMED",
        actorId=current_user.id,
        meta={"method": "CLIENT_CONFIRM", "razorpayPaymentId": payload.razorpayPaymentId}
    )
    db.add(event)
    await db.commit()

    return success_response("Payment confirmed successfully", data={
        "id": booking.id,
        "status": booking.status.value,
        "paymentStatus": booking.paymentStatus,
        "paymentId": booking.paymentId
    })


@router.post("/payment-failure")
async def handle_payment_failure(
    payload: PaymentFailureRequest,
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == payload.bookingId)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.userId != current_user.id:
        return error_response("Booking not found", status_code=404)

    if booking.status != BookingStatus.PAYMENT_PENDING:
        return error_response("Only pending payments can be marked as failed", status_code=400)

    booking.status = BookingStatus.PAYMENT_FAILED
    booking.holdExpiresAt = None
    db.add(booking)

    # Log event
    event = BookingEvent(
        bookingId=booking.id,
        fromStatus="PAYMENT_PENDING",
        toStatus="PAYMENT_FAILED",
        actorId=current_user.id,
        meta={"reason": payload.reason}
    )
    db.add(event)
    await db.commit()

    return success_response("Booking updated to failed state")


@router.post("/webhook/razorpay")
async def handle_payment_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")

    # Verify signature
    is_valid = verify_webhook_signature(body_str, x_razorpay_signature)
    if not is_valid:
        return error_response("Invalid signature", status_code=400)

    try:
        event_payload = json.loads(body_str)
        event = event_payload.get("event")
        payload = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
        booking_id = payload.get("notes", {}).get("bookingId")

        if event in ("payment.captured", "order.paid") and booking_id:
            # Fetch booking
            stmt = select(Booking).where(Booking.id == booking_id)
            res = await db.execute(stmt)
            booking = res.scalar_one_or_none()

            if booking and booking.status != BookingStatus.CONFIRMED:
                # Update booking status
                total = booking.amount
                base_amount = total / 1.18
                gst_amount = total - base_amount
                commission_amount = base_amount * 0.10
                provider_amount = base_amount - commission_amount

                booking.status = BookingStatus.CONFIRMED
                booking.paymentStatus = "PAID"
                booking.paymentId = payload.get("id")
                booking.orderId = payload.get("order_id")
                booking.baseAmount = base_amount
                booking.gstAmount = gst_amount
                booking.commissionAmount = commission_amount
                booking.providerAmount = provider_amount
                booking.holdExpiresAt = None
                db.add(booking)

                # Event log
                event_log = BookingEvent(
                    bookingId=booking.id,
                    fromStatus=booking.status.value,
                    toStatus="CONFIRMED",
                    actorId="RAZORPAY_WEBHOOK",
                    meta={"razorpayEvent": event}
                )
                db.add(event_log)

                # Notification for provider
                notification = Notification(
                    userId=booking.providerId,
                    title="New Booking (Auto-Confirmed)!",
                    message=f"A job for {booking.slot} was confirmed via payment.",
                    type="BOOKING_CONFIRMED"
                )
                db.add(notification)

                # Payout record
                p_profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == booking.providerId)
                p_profile_res = await db.execute(p_profile_stmt)
                p_profile = p_profile_res.scalar_one_or_none()

                if p_profile:
                    payout = PayoutRecord(
                        providerId=booking.providerId,
                        bookingId=booking.id,
                        amount=provider_amount,
                        status="PENDING",
                        bankName=p_profile.bankName or "Unknown",
                        bankAccountName=p_profile.bankAccountName or "Unknown",
                        bankAccountNumber=p_profile.bankAccountNumber or "Unknown",
                        bankIFSC=p_profile.bankIFSC or "Unknown"
                    )
                    db.add(payout)

                await db.commit()
    except Exception as e:
        print(f"Webhook processing error: {e}")
        return error_response("Webhook processing failed", status_code=500)

    return success_response("Webhook processed")


@router.get("/user/dashboard")
async def get_user_dashboard_data(
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    # Active bookings (CONFIRMED/IN_PROGRESS)
    active_stmt = (
        select(Booking)
        .where(Booking.userId == current_user.id, Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS]))
        .options(
            selectinload(Booking.provider),
            selectinload(Booking.service)
        )
        .order_by(Booking.dateTime.asc())
    )
    active_res = await db.execute(active_stmt)
    active_bookings = active_res.scalars().all()

    # Completed bookings count
    completed_stmt = select(func.count(Booking.id)).where(Booking.userId == current_user.id, Booking.status == BookingStatus.COMPLETED)
    completed_res = await db.execute(completed_stmt)
    completed_count = completed_res.scalar_one() or 0

    # Total Spent
    spent_stmt = select(func.sum(Booking.amount)).where(Booking.userId == current_user.id, Booking.status == BookingStatus.COMPLETED)
    spent_res = await db.execute(spent_stmt)
    total_spent = spent_res.scalar_one() or 0.0

    active_bookings_list = []
    for b in active_bookings:
        active_bookings_list.append({
            "id": b.id,
            "status": b.status.value,
            "dateTime": b.dateTime.isoformat(),
            "slot": b.slot,
            "address": b.address,
            "amount": b.amount,
            "provider": {"fullName": b.provider.fullName} if b.provider else None,
            "service": {"title": b.service.title, "images": b.service.images} if b.service else None
        })

    next_job = active_bookings_list[0] if active_bookings_list else None

    return success_response(
        "User dashboard data fetched",
        data={
            "activeBookings": active_bookings_list,
            "completedCount": completed_count,
            "totalSpent": float(total_spent),
            "nextJob": next_job
        }
    )


@router.get("/provider/dashboard")
async def get_provider_dashboard_data(
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    # Completed jobs stats (count & total sum)
    completed_stmt = (
        select(func.count(Booking.id), func.sum(Booking.amount))
        .where(Booking.providerId == current_user.id, Booking.status == BookingStatus.COMPLETED)
    )
    completed_res = await db.execute(completed_stmt)
    jobs_count, earnings_sum = completed_res.one()
    jobs_count = jobs_count or 0
    earnings_sum = earnings_sum or 0.0

    # Today's completed jobs earnings
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_stmt = (
        select(func.sum(Booking.amount))
        .where(
            Booking.providerId == current_user.id,
            Booking.status == BookingStatus.COMPLETED,
            Booking.updatedAt >= today_start
        )
    )
    today_res = await db.execute(today_stmt)
    today_earnings = today_res.scalar_one() or 0.0

    # Upcoming bookings (CONFIRMED and future)
    upcoming_stmt = (
        select(Booking)
        .where(
            Booking.providerId == current_user.id,
            Booking.status == BookingStatus.CONFIRMED,
            Booking.dateTime >= datetime.utcnow()
        )
        .options(
            selectinload(Booking.user),
            selectinload(Booking.service)
        )
        .order_by(Booking.dateTime.asc())
        .limit(10)
    )
    upcoming_res = await db.execute(upcoming_stmt)
    upcoming_bookings = upcoming_res.scalars().all()

    # Recent reviews (limit 5)
    reviews_stmt = (
        select(Review)
        .where(Review.providerId == current_user.id)
        .options(selectinload(Review.user))
        .order_by(Review.createdAt.desc())
        .limit(5)
    )
    reviews_res = await db.execute(reviews_stmt)
    recent_reviews = reviews_res.scalars().all()

    # Online status & Bank details requirement
    profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
    profile_res = await db.execute(profile_stmt)
    profile = profile_res.scalar_one_or_none()

    requires_bank_update = True
    is_online = True
    if profile:
        is_online = profile.isOnline
        if profile.bankName and profile.bankAccountName and profile.bankAccountNumber and profile.bankIFSC:
            requires_bank_update = False

    upcoming_list = []
    for b in upcoming_bookings:
        upcoming_list.append({
            "id": b.id,
            "dateTime": b.dateTime.isoformat(),
            "slot": b.slot,
            "address": b.address,
            "amount": b.amount,
            "user": {"fullName": b.user.fullName, "phone": b.user.phone} if b.user else None,
            "service": {"title": b.service.title} if b.service else None
        })

    recent_reviews_list = []
    for r in recent_reviews:
        recent_reviews_list.append({
            "id": r.id,
            "rating": r.rating,
            "comment": r.comment,
            "createdAt": r.createdAt.isoformat(),
            "user": {"fullName": r.user.fullName} if r.user else None
        })

    return success_response(
        "Dashboard data fetched",
        data={
            "totalEarnings": float(earnings_sum),
            "completedJobs": jobs_count,
            "todayEarnings": float(today_earnings),
            "upcomingBookings": upcoming_list,
            "recentReviews": recent_reviews_list,
            "isOnline": is_online,
            "requiresBankUpdate": requires_bank_update
        }
    )


@router.get("/my")
async def get_user_bookings(
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Booking)
        .where(Booking.userId == current_user.id)
        .options(
            selectinload(Booking.provider).selectinload(User.providerProfile),
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
            "paymentId": b.paymentId,
            "orderId": b.orderId,
            "createdAt": b.createdAt.isoformat(),
            "provider": {
                "fullName": b.provider.fullName,
                "providerProfile": {"businessName": b.provider.providerProfile.businessName} if b.provider.providerProfile else None
            } if b.provider else None,
            "service": {
                "title": b.service.title,
                "category": b.service.category,
                "images": b.service.images
            } if b.service else None
        })

    return success_response("User bookings fetched", data=bookings_list)


@router.get("/provider")
async def get_provider_bookings(
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Booking)
        .where(Booking.providerId == current_user.id)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.service)
        )
        .order_by(Booking.dateTime.asc())
    )
    res = await db.execute(stmt)
    bookings = res.scalars().all()

    bookings_list = []
    for b in bookings:
        bookings_list.append({
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
            "paymentId": b.paymentId,
            "orderId": b.orderId,
            "createdAt": b.createdAt.isoformat(),
            "user": {
                "fullName": b.user.fullName,
                "phone": b.user.phone
            } if b.user else None,
            "service": {
                "title": b.service.title
            } if b.service else None
        })

    return success_response("Provider bookings fetched", data=bookings_list)


@router.patch("/{id}/accept")
async def accept_booking(
    id: str,
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.providerId != current_user.id:
        return error_response("Not authorized to accept this job", status_code=401)

    old_status = booking.status.value
    booking.status = BookingStatus.ACCEPTED
    db.add(booking)

    event = BookingEvent(
        bookingId=booking.id,
        fromStatus=old_status,
        toStatus="ACCEPTED",
        actorId=current_user.id
    )
    db.add(event)
    await db.commit()
    return success_response("Job accepted successfully")


@router.patch("/{id}/reject")
async def reject_booking(
    id: str,
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.providerId != current_user.id:
        return error_response("Not authorized to reject this job", status_code=401)

    old_status = booking.status.value
    booking.status = BookingStatus.REJECTED
    db.add(booking)

    event = BookingEvent(
        bookingId=booking.id,
        fromStatus=old_status,
        toStatus="REJECTED",
        actorId=current_user.id
    )
    db.add(event)
    await db.commit()
    return success_response("Job rejected successfully")


@router.patch("/{id}/start")
async def start_booking(
    id: str,
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.providerId != current_user.id:
        return error_response("Not authorized to start this job", status_code=401)

    old_status = booking.status.value
    booking.status = BookingStatus.IN_PROGRESS
    db.add(booking)

    event = BookingEvent(
        bookingId=booking.id,
        fromStatus=old_status,
        toStatus="IN_PROGRESS",
        actorId=current_user.id
    )
    db.add(event)
    await db.commit()
    return success_response("Job started successfully")


@router.patch("/{id}/complete")
async def complete_booking(
    id: str,
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.providerId != current_user.id:
        return error_response("Not authorized to complete this job", status_code=401)

    booking.status = BookingStatus.COMPLETED
    db.add(booking)

    # Event log
    event = BookingEvent(
        bookingId=booking.id,
        fromStatus=booking.status.value,
        toStatus="COMPLETED",
        actorId=current_user.id
    )
    db.add(event)

    # Increment completed jobs in provider profile
    p_profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
    p_profile_res = await db.execute(p_profile_stmt)
    p_profile = p_profile_res.scalar_one_or_none()
    if p_profile:
        p_profile.totalJobs += 1
        db.add(p_profile)

    await db.commit()

    return success_response("Job marked as completed")


@router.patch("/{id}/cancel")
async def cancel_booking(
    id: str,
    payload: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.userId != current_user.id:
        return error_response("Booking not found", status_code=404)

    if booking.status in (BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.REJECTED):
        return error_response("Booking cannot be cancelled in its current state", status_code=400)

    old_status = booking.status.value
    booking.status = BookingStatus.CANCELLED
    booking.holdExpiresAt = None
    db.add(booking)

    # Event log
    event = BookingEvent(
        bookingId=booking.id,
        fromStatus=old_status,
        toStatus="CANCELLED",
        actorId=current_user.id,
        meta={"reason": payload.reason or "Cancelled by user"}
    )
    db.add(event)
    await db.commit()

    return success_response("Booking cancelled successfully", data={
        "id": booking.id,
        "status": booking.status.value
    })


@router.patch("/{id}/reschedule")
async def reschedule_booking(
    id: str,
    payload: RescheduleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.userId != current_user.id:
        return error_response("Booking not found", status_code=404)

    old_date = booking.dateTime
    new_date = datetime.fromisoformat(payload.scheduledDate.replace('Z', '+00:00')).replace(tzinfo=None)
    old_status = booking.status.value

    booking.dateTime = new_date
    booking.slot = payload.slot
    booking.status = BookingStatus.PENDING
    db.add(booking)

    # Event log
    event = BookingEvent(
        bookingId=booking.id,
        fromStatus=old_status,
        toStatus="PENDING",
        actorId=current_user.id,
        meta={"oldDate": old_date.isoformat(), "newDate": new_date.isoformat()}
    )
    db.add(event)
    await db.commit()

    return success_response("Booking rescheduled successfully", data={
        "id": booking.id,
        "dateTime": booking.dateTime.isoformat(),
        "slot": booking.slot,
        "status": booking.status.value
    })


@router.post("/{id}/retry-payment")
async def retry_payment(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Booking).where(Booking.id == id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking or booking.userId != current_user.id:
        return error_response("Booking not found", status_code=404)

    if booking.paymentStatus == "PAID":
        return error_response("Booking is already paid", status_code=400)

    try:
        order = create_razorpay_order(booking.amount, booking.id)
        booking.orderId = order["id"]
        db.add(booking)
        await db.commit()
    except Exception:
        return error_response("Failed to retry payment", status_code=500)

    return success_response("Payment retry initiated", data={
        "booking": {
            "id": booking.id,
            "orderId": booking.orderId,
            "amount": booking.amount
        },
        "razorpayOrder": order
    })


@router.post("/cleanup-expired")
async def cleanup_expired_bookings(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Booking)
        .where(
            Booking.status == BookingStatus.PAYMENT_PENDING,
            Booking.holdExpiresAt < datetime.utcnow()
        )
    )
    res = await db.execute(stmt)
    expired = res.scalars().all()

    count = 0
    for b in expired:
        b.status = BookingStatus.EXPIRED
        b.holdExpiresAt = None
        db.add(b)
        count += 1

    await db.commit()
    return success_response(f"{count} abandoned bookings marked as EXPIRED")
