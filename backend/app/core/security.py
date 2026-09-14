"""JWT + bcrypt 유틸. 회원가입/로그인/JWT 의존성에서 공통으로 사용.

설계 메모:
- bcrypt 12 라운드 (passlib 기본). 더 올리면 로그인이 느려져 brute-force 방지에는 좋지만 UX에 영향.
- JWT 는 access-only (refresh 토큰 미사용). 만료는 settings.JWT_ACCESS_EXPIRE_MIN.
- 비밀번호 검증 실패 시 사용자 존재/비번오류 메시지를 동일하게 (유저 enumeration 방지).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.core.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(sub: str, extra: Optional[dict] = None,
                        expires_min: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_min or settings.JWT_ACCESS_EXPIRE_MIN)
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
