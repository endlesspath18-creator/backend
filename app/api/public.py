from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.extra import Banner
from app.models.category import Category
from app.utils.response import success_response, error_response

router = APIRouter(prefix="/public", tags=["Public"])

@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    stmt = select(Category).where(Category.isActive == True).order_by(Category.title.asc())
    res = await db.execute(stmt)
    categories = res.scalars().all()
    
    categories_list = []
    for c in categories:
        categories_list.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "image": c.image,
            "icon": c.icon,
            "isActive": c.isActive
        })
    return success_response("Categories fetched successfully", data=categories_list)


@router.get("/banners")
async def get_public_banners(db: AsyncSession = Depends(get_db)):
    stmt = select(Banner).where(Banner.isActive == True).order_by(Banner.createdAt.desc())
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
    return success_response("Banners fetched successfully", data=banners_list)


@router.get("/top-providers")
async def get_top_providers(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(User)
        .join(ProviderProfile)
        .where(User.role == Role.PROVIDER)
        .options(selectinload(User.providerProfile))
        .order_by(ProviderProfile.rating.desc())
        .limit(10)
    )
    res = await db.execute(stmt)
    providers = res.scalars().all()
    
    providers_list = []
    for p in providers:
        profile_dict = None
        if p.providerProfile:
            profile_dict = {
                "id": p.providerProfile.id,
                "userId": p.providerProfile.userId,
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
            "isRoleSet": p.isRoleSet,
            "isActive": p.isActive,
            "profileImage": p.profileImage,
            "providerProfile": profile_dict
        })
        
    return success_response("Top providers fetched", data=providers_list)
