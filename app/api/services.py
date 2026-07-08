from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, and_

from app.database.session import get_db
from app.models.user import User, Role
from app.models.provider import ProviderProfile
from app.models.service import Service, ServiceStatus
from app.schemas.all_schemas import ServiceCreate, ServiceUpdate
from app.utils.response import success_response, error_response
from app.api.deps import get_current_user, require_role, get_current_provider

router = APIRouter(prefix="/services", tags=["Services"])

# Category default stock images
CATEGORY_IMAGES = {
    "ac repair": ["https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=600&q=80"],
    "plumbing": ["https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?auto=format&fit=crop&w=600&q=80"],
    "electrical": ["https://images.unsplash.com/photo-1621905252507-b354bc25edac?auto=format&fit=crop&w=600&q=80"],
    "cleaning": ["https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=600&q=80"],
    "appliance repair": ["https://images.unsplash.com/photo-1581092921461-eab62e97a780?auto=format&fit=crop&w=600&q=80"],
    "mechanical works": ["https://images.unsplash.com/photo-1486006920555-c77dce18193b?auto=format&fit=crop&w=600&q=80"],
}

def get_default_images(category: str) -> list[str]:
    cat_lower = category.lower().strip()
    return CATEGORY_IMAGES.get(cat_lower, ["https://images.unsplash.com/photo-1581092921461-eab62e97a780?auto=format&fit=crop&w=600&q=80"])


@router.get("")
async def get_services(
    category: str | None = None,
    providerId: str | None = None,
    searchQuery: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    # Base filter
    filters = [Service.isActive == True]
    
    if not providerId:
        filters.append(Service.status == ServiceStatus.AVAILABLE)
    else:
        filters.append(Service.providerId == providerId)
        
    if category:
        filters.append(Service.category == category)
        
    if searchQuery:
        filters.append(
            or_(
                Service.title.ilike(f"%{searchQuery}%"),
                Service.description.ilike(f"%{searchQuery}%")
            )
        )
        
    query = (
        select(Service)
        .where(and_(*filters))
        .options(
            selectinload(Service.provider).selectinload(User.providerProfile)
        )
        .order_by(Service.createdAt.desc())
    )
    
    result = await db.execute(query)
    services = result.scalars().all()
    
    # Map to nested provider representation expected by mobile app
    services_list = []
    for s in services:
        provider_dict = None
        if s.provider:
            profile_dict = None
            if s.provider.providerProfile:
                profile_dict = {
                    "businessName": s.provider.providerProfile.businessName,
                    "rating": s.provider.providerProfile.rating,
                    "isOnline": s.provider.providerProfile.isOnline
                }
            provider_dict = {
                "id": s.provider.id,
                "fullName": s.provider.fullName,
                "providerProfile": profile_dict
            }
            
        services_list.append({
            "id": s.id,
            "providerId": s.providerId,
            "title": s.title,
            "category": s.category,
            "description": s.description,
            "price": s.price,
            "durationMinutes": s.durationMinutes,
            "status": s.status.value,
            "isActive": s.isActive,
            "images": s.images,
            "rating": s.rating,
            "totalJobs": s.totalJobs,
            "createdAt": s.createdAt.isoformat(),
            "updatedAt": s.updatedAt.isoformat(),
            "provider": provider_dict
        })
        
    return success_response("Services fetched successfully", data=services_list)


@router.get("/my")
async def get_my_services(
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    query = (
        select(Service)
        .where(Service.providerId == current_user.id)
        .order_by(Service.createdAt.desc())
    )
    result = await db.execute(query)
    services = result.scalars().all()
    
    services_list = []
    for s in services:
        services_list.append({
            "id": s.id,
            "providerId": s.providerId,
            "title": s.title,
            "category": s.category,
            "description": s.description,
            "price": s.price,
            "durationMinutes": s.durationMinutes,
            "status": s.status.value,
            "isActive": s.isActive,
            "images": s.images,
            "rating": s.rating,
            "totalJobs": s.totalJobs,
            "createdAt": s.createdAt.isoformat(),
            "updatedAt": s.updatedAt.isoformat()
        })
        
    return success_response("Provider services fetched", data=services_list)


@router.get("/{id}")
async def get_service_by_id(id: str, db: AsyncSession = Depends(get_db)):
    query = (
        select(Service)
        .where(Service.id == id)
        .options(
            selectinload(Service.provider).selectinload(User.providerProfile)
        )
    )
    result = await db.execute(query)
    service = result.scalar_one_or_none()
    if not service:
        return error_response("Service not found", status_code=404)
        
    provider_dict = None
    if service.provider:
        provider_dict = {
            "id": service.provider.id,
            "fullName": service.provider.fullName,
            "providerProfile": {
                "id": service.provider.providerProfile.id if service.provider.providerProfile else None,
                "userId": service.provider.id,
                "businessName": service.provider.providerProfile.businessName if service.provider.providerProfile else None,
                "bio": service.provider.providerProfile.bio if service.provider.providerProfile else None,
                "experienceYears": service.provider.providerProfile.experienceYears if service.provider.providerProfile else 0,
                "rating": service.provider.providerProfile.rating if service.provider.providerProfile else 0.0,
                "totalJobs": service.provider.providerProfile.totalJobs if service.provider.providerProfile else 0,
                "isOnline": service.provider.providerProfile.isOnline if service.provider.providerProfile else True
            } if service.provider.providerProfile else None
        }
        
    service_dict = {
        "id": service.id,
        "providerId": service.providerId,
        "title": service.title,
        "category": service.category,
        "description": service.description,
        "price": service.price,
        "durationMinutes": service.durationMinutes,
        "status": service.status.value,
        "isActive": service.isActive,
        "images": service.images,
        "rating": service.rating,
        "totalJobs": service.totalJobs,
        "createdAt": service.createdAt.isoformat(),
        "updatedAt": service.updatedAt.isoformat(),
        "provider": provider_dict
    }
    return success_response("Service fetched successfully", data=service_dict)


@router.post("")
async def create_service(
    payload: ServiceCreate,
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.canPublishService:
        return error_response("Please pay the activation fee to publish services", status_code=403)
        
    images = payload.images if payload.images else get_default_images(payload.category)
    
    new_service = Service(
        providerId=current_user.id,
        title=payload.title,
        category=payload.category,
        description=payload.description,
        price=payload.price,
        durationMinutes=payload.durationMinutes,
        images=images,
        status=ServiceStatus.AVAILABLE,
        isActive=True
    )
    
    db.add(new_service)
    await db.commit()
    await db.refresh(new_service)
    
    service_dict = {
        "id": new_service.id,
        "providerId": new_service.providerId,
        "title": new_service.title,
        "category": new_service.category,
        "description": new_service.description,
        "price": new_service.price,
        "durationMinutes": new_service.durationMinutes,
        "status": new_service.status.value,
        "isActive": new_service.isActive,
        "images": new_service.images,
        "rating": new_service.rating,
        "totalJobs": new_service.totalJobs,
        "createdAt": new_service.createdAt.isoformat(),
        "updatedAt": new_service.updatedAt.isoformat()
    }
    return success_response("Service created successfully", data=service_dict, status_code=201)


@router.patch("/{id}")
async def update_service(
    id: str,
    payload: ServiceUpdate,
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).where(Service.id == id)
    )
    service = result.scalar_one_or_none()
    if not service:
        return error_response("Service not found", status_code=404)
        
    if service.providerId != current_user.id:
        return error_response("Not authorized to update this service", status_code=403)
        
    # Apply updates
    if payload.title is not None:
        service.title = payload.title
    if payload.category is not None:
        service.category = payload.category
        if not payload.images:
            service.images = get_default_images(payload.category)
    if payload.description is not None:
        service.description = payload.description
    if payload.price is not None:
        service.price = payload.price
    if payload.durationMinutes is not None:
        service.durationMinutes = payload.durationMinutes
    if payload.images is not None:
        service.images = payload.images
    if payload.status is not None:
        service.status = payload.status
    if payload.isActive is not None:
        service.isActive = payload.isActive
        
    db.add(service)
    await db.commit()
    await db.refresh(service)
    
    service_dict = {
        "id": service.id,
        "providerId": service.providerId,
        "title": service.title,
        "category": service.category,
        "description": service.description,
        "price": service.price,
        "durationMinutes": service.durationMinutes,
        "status": service.status.value,
        "isActive": service.isActive,
        "images": service.images,
        "rating": service.rating,
        "totalJobs": service.totalJobs,
        "createdAt": service.createdAt.isoformat(),
        "updatedAt": service.updatedAt.isoformat()
    }
    return success_response("Service updated successfully", data=service_dict)


@router.delete("/{id}")
async def delete_service(
    id: str,
    current_user: User = Depends(get_current_provider),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).where(Service.id == id)
    )
    service = result.scalar_one_or_none()
    if not service:
        return error_response("Service not found", status_code=404)
        
    if service.providerId != current_user.id:
        return error_response("Not authorized to delete this service", status_code=403)
        
    await db.delete(service)
    await db.commit()
    return success_response("Service deleted successfully")
