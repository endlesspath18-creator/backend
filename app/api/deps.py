from typing import AsyncGenerator, Annotated
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database.session import get_db
from app.core.security import verify_token
from app.models.user import User, Role
from app.models.provider import ProviderProfile

# Custom HTTP Exceptions mapping to JSON response format expected by client
class AuthException(HTTPException):
    def __init__(self, detail: str, status_code: int = 401):
        super().__init__(status_code=status_code, detail=detail)

async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthException("Not authorized to access this route")
    
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload:
        raise AuthException("Not authorized to access this route")
    
    user_id = payload.get("id")
    if not user_id:
        raise AuthException("Not authorized to access this route")
        
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise AuthException("User no longer exists")
        
    if not user.isActive:
        raise AuthException("User account is deactivated", status_code=403)
        
    # Role validation check to prevent session collisions
    token_role = payload.get("role")
    if token_role and token_role != user.role.value:
        raise AuthException("Role mismatch, please login again")
        
    return user

def require_role(allowed_role: Role):
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != allowed_role:
            raise AuthException(
                f"Forbidden: Only {allowed_role.value} can access this route",
                status_code=403
            )
        return current_user
    return role_checker

async def get_current_provider(
    current_user: User = Depends(require_role(Role.PROVIDER)),
    db: AsyncSession = Depends(get_db)
) -> User:
    # Double check if provider profile exists
    result = await db.execute(
        select(ProviderProfile).where(ProviderProfile.userId == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise AuthException("Provider profile not found", status_code=404)
    return current_user

async def get_current_admin(
    current_user: User = Depends(require_role(Role.ADMIN))
) -> User:
    return current_user
