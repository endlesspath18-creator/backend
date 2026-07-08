from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.booking import Booking, BookingStatus
from app.models.extra import Review
from app.schemas.all_schemas import ReviewCreate
from app.utils.response import success_response, error_response
from app.api.deps import require_role

router = APIRouter(prefix="/reviews", tags=["Reviews"])

@router.post("")
async def create_review(
    payload: ReviewCreate,
    current_user: User = Depends(require_role(Role.USER)),
    db: AsyncSession = Depends(get_db)
):
    # Fetch booking
    stmt = select(Booking).where(Booking.id == payload.bookingId)
    res = await db.execute(stmt)
    booking = res.scalar_one_or_none()

    if not booking:
        return error_response("Booking not found", status_code=404)

    if booking.userId != current_user.id:
        return error_response("Not authorized to review this booking", status_code=401)

    if booking.status != BookingStatus.COMPLETED:
        return error_response("Can only review completed bookings", status_code=400)

    # Check duplicate review
    rev_stmt = select(Review).where(Review.bookingId == payload.bookingId)
    rev_res = await db.execute(rev_stmt)
    if rev_res.scalar_one_or_none():
        return error_response("Review already exists for this booking", status_code=400)

    # Create Review
    new_review = Review(
        bookingId=booking.id,
        userId=current_user.id,
        providerId=booking.providerId,
        rating=payload.rating,
        comment=payload.comment
    )
    db.add(new_review)
    await db.commit()
    await db.refresh(new_review)

    # Re-calculate Provider average rating
    all_reviews_stmt = select(func.avg(Review.rating)).where(Review.providerId == booking.providerId)
    all_reviews_res = await db.execute(all_reviews_stmt)
    avg_rating = all_reviews_res.scalar_one() or 0.0

    # Update ProviderProfile rating
    profile_stmt = select(ProviderProfile).where(ProviderProfile.userId == booking.providerId)
    profile_res = await db.execute(profile_stmt)
    profile = profile_res.scalar_one_or_none()
    if profile:
        profile.rating = float(round(avg_rating, 2))
        db.add(profile)
        await db.commit()

    return success_response("Review created successfully", data={
        "id": new_review.id,
        "bookingId": new_review.bookingId,
        "userId": new_review.userId,
        "providerId": new_review.providerId,
        "rating": new_review.rating,
        "comment": new_review.comment,
        "createdAt": new_review.createdAt.isoformat()
    }, status_code=201)


@router.get("/provider/{providerId}")
async def get_provider_reviews(
    providerId: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Review)
        .where(Review.providerId == providerId)
        .options(selectinload(Review.user))
        .order_by(Review.createdAt.desc())
    )
    res = await db.execute(stmt)
    reviews = res.scalars().all()

    reviews_list = []
    for r in reviews:
        reviews_list.append({
            "id": r.id,
            "bookingId": r.bookingId,
            "userId": r.userId,
            "providerId": r.providerId,
            "rating": r.rating,
            "comment": r.comment,
            "createdAt": r.createdAt.isoformat(),
            "user": {"fullName": r.user.fullName, "profileImage": r.user.profileImage} if r.user else None
        })

    return success_response("Provider reviews fetched", data=reviews_list)
