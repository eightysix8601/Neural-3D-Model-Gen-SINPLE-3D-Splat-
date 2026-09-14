"""FastAPI dependencies (auth).

토큰은 두 경로로 받는다:
1) `Authorization: Bearer <jwt>` 헤더 — 일반 API
2) `?token=<jwt>` 쿼리 — three.js GLTFLoader, <a href> 다운로드 등
   인증 헤더를 못 끼우는 곳을 위한 fallback (same-origin SPA 한정).
"""
from typing import Optional
import uuid
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models.user import User
from app.core.security import decode_access_token

oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
oauth2_required = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)


async def _user_from_token(token: Optional[str], db: AsyncSession) -> Optional[User]:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        uid = uuid.UUID(sub)
    except (ValueError, TypeError):
        return None
    r = await db.execute(select(User).where(User.id == uid, User.is_active == True))
    return r.scalar_one_or_none()


async def get_current_user(token: str = Depends(oauth2_required),
                           db: AsyncSession = Depends(get_db)) -> User:
    user = await _user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="인증 실패", headers={"WWW-Authenticate": "Bearer"})
    return user


async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_optional),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    # 1) Authorization 헤더 우선
    if token:
        u = await _user_from_token(token, db)
        if u:
            return u
    # 2) ?token= 쿼리 fallback (헤더 못 보내는 fetch/href 용)
    q = request.query_params.get("token")
    if q:
        return await _user_from_token(q, db)
    return None
