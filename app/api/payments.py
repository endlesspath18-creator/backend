from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.service import Service
from app.models.booking import Booking, BookingStatus, PayoutRecord
from app.models.payment import PaymentTransaction
from app.schemas.all_schemas import ConfirmPaymentRequest
from app.utils.response import success_response, error_response
from app.utils.razorpay import create_razorpay_order, verify_razorpay_signature
from app.api.deps import get_current_user, require_role, get_current_provider
from app.core.config import settings

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("/create-order")
async def create_booking_payment_order(
    payload: dict,
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    booking_id = payload.get("bookingId")
    if not booking_id:
        return error_response("bookingId is required", status_code=400)
        
    stmt = select(Booking).where(Booking.id == booking_id)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()
    
    if not booking:
        return error_response("Booking not found", status_code=404)
        
    try:
        order = create_razorpay_order(booking.amount, booking.id)
        
        # Save orderId to booking
        booking.orderId = order["id"]
        db.add(booking)
        await db.commit()
        
        return success_response("Razorpay order created", data={
            "orderId": order["id"],
            "amount": booking.amount,
            "currency": "INR",
            "key": settings.RAZORPAY_KEY_ID
        }, status_code=201)
    except Exception as e:
        print(f"Razorpay Order Error: {e}")
        return error_response("Failed to create payment order", status_code=500)


@router.post("/verify")
async def verify_booking_payment(
    payload: ConfirmPaymentRequest,
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    # Verify Signature
    is_valid = verify_razorpay_signature(payload.razorpayOrderId, payload.razorpayPaymentId, payload.razorpaySignature)
    if not is_valid:
        return error_response("Payment verification failed: Invalid signature", status_code=400)
        
    # Replay attack check
    tx_stmt = select(PaymentTransaction).where(PaymentTransaction.paymentId == payload.razorpayPaymentId)
    tx_res = await db.execute(tx_stmt)
    existing_tx = tx_res.scalar_one_or_none()
    if existing_tx:
        return success_response("Payment already processed", data=existing_tx)
        
    # Process within transaction
    stmt = select(Booking).where(Booking.id == payload.bookingId)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()
    
    if not booking:
        return error_response("Booking record not found", status_code=404)
    if booking.userId != current_user.id:
        return error_response("Fraud detected: Booking does not belong to user", status_code=403)
    if booking.orderId != payload.razorpayOrderId:
        return error_response("Payment security breach: Order ID mismatch", status_code=400)
        
    # Update Booking
    booking.paymentStatus = "PAID"
    booking.status = BookingStatus.CONFIRMED
    booking.paymentId = payload.razorpayPaymentId
    booking.holdExpiresAt = None
    db.add(booking)
    
    # Calculate split
    total = booking.amount
    base_amount = total / 1.18
    gst_amount = total - base_amount
    commission_amount = base_amount * 0.10
    provider_amount = base_amount - commission_amount
    
    # Create PaymentTransaction record
    transaction = PaymentTransaction(
        userId=current_user.id,
        type="BOOKING",
        amount=total,
        gstAmount=gst_amount,
        commissionAmount=commission_amount,
        providerAmount=provider_amount,
        status="SUCCESS",
        paymentId=payload.razorpayPaymentId,
        orderId=payload.razorpayOrderId,
        gatewayResponse=payload.model_dump(),
        bookingId=booking.id
    )
    db.add(transaction)
    
    # Create Payout record
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
    return success_response("Payment verified successfully", data=booking)


@router.post("/activation/create-order")
async def create_activation_order(
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    if current_user.hasPaidPublishingFee:
        return error_response("Your account is already activated", status_code=400)
        
    amount = 300.0 # Provider activation fee is ₹300
    try:
        order = create_razorpay_order(amount, current_user.id)
        return success_response("Activation order created", data={
            "orderId": order["id"],
            "amount": amount,
            "currency": "INR",
            "key": settings.RAZORPAY_KEY_ID
        }, status_code=201)
    except Exception as e:
        print(f"ACTIVATION_ORDER_ERROR: {e}")
        return error_response("Secure activation order creation failed", status_code=500)


@router.post("/activation/verify")
async def verify_activation_payment(
    payload: dict,
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
):
    razorpay_order_id = payload.get("razorpay_order_id")
    razorpay_payment_id = payload.get("razorpay_payment_id")
    razorpay_signature = payload.get("razorpay_signature")
    
    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return error_response("Missing required parameters", status_code=400)
        
    # Verify Signature
    is_valid = verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature)
    if not is_valid:
        return error_response("Activation verification failed", status_code=400)
        
    # Replay attack check
    tx_stmt = select(PaymentTransaction).where(PaymentTransaction.paymentId == razorpay_payment_id)
    tx_res = await db.execute(tx_stmt)
    if tx_res.scalar_one_or_none():
        return success_response("Activation already processed")
        
    # Update User Publishing privileges
    current_user.hasPaidPublishingFee = True
    current_user.canPublishService = True
    db.add(current_user)
    
    # Create PaymentTransaction log
    transaction = PaymentTransaction(
        userId=current_user.id,
        type="PROVIDER_ACTIVATION",
        amount=300.0,
        commissionAmount=300.0, # 100% platform revenue
        providerAmount=0.0,
        status="SUCCESS",
        paymentId=razorpay_payment_id,
        orderId=razorpay_order_id,
        gatewayResponse=payload
    )
    db.add(transaction)
    await db.commit()
    
    return success_response("Account activated securely", data=current_user)


@router.get("/history")
async def get_payment_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Booking)
        .where(
            Booking.userId == current_user.id,
            Booking.paymentMethod == "ONLINE",
            Booking.paymentStatus == "PAID"
        )
        .options(
            selectinload(Booking.service),
            selectinload(Booking.provider)
        )
        .order_by(Booking.createdAt.desc())
    )
    res = await db.execute(stmt)
    bookings = res.scalars().all()
    
    history = []
    for b in bookings:
        history.append({
            "id": b.id,
            "amount": b.amount,
            "paymentId": b.paymentId,
            "orderId": b.orderId,
            "createdAt": b.createdAt.isoformat(),
            "service": {"title": b.service.title, "category": b.service.category} if b.service else None,
            "provider": {"fullName": b.provider.fullName} if b.provider else None
        })
        
    return success_response("Payment history fetched", data=history)
