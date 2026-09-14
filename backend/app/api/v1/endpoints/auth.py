"""Auth API: 회원가입 / 로그인 / 현재 사용자

보안 메모:
- 비밀번호는 bcrypt 로 해시 후 저장. 평문은 절대 로깅하지 않음.
- 로그인 실패 시 메시지를 "이메일 또는 비밀번호가 올바르지 않습니다"로 통일 → 사용자 enumeration 방어.
- 응답에 password_hash 가 포함되지 않도록 UserResponse 사용.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from loguru import logger
from app.db.session import get_db
from app.db.models.user import User
from app.schemas.user import UserRegister, UserLogin, UserResponse, TokenResponse
from app.core.security import hash_password, verify_password, create_access_token
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    email_l = body.email.lower()
    # 중복 검증 (대소문자 무시)
    r = await db.execute(select(User).where(or_(
        func.lower(User.email) == email_l,
        func.lower(User.username) == body.username.lower(),
    )))
    if r.scalar_one_or_none():
        raise HTTPException(409, "이미 사용 중인 이메일 또는 사용자명입니다")
    user = User(email=email_l, username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    logger.info(f"[Auth] 신규 가입: {user.username} ({user.email})")
    token = create_access_token(sub=str(user.id), extra={"username": user.username})
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login_json(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """JSON 본문으로 로그인. 프론트엔드 fetch 와 동일한 형식."""
    ident = body.identifier.strip().lower()
    r = await db.execute(select(User).where(or_(
        func.lower(User.email) == ident,
        func.lower(User.username) == ident,
    )))
    user = r.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "이메일/사용자명 또는 비밀번호가 올바르지 않습니다")
    token = create_access_token(sub=str(user.id), extra={"username": user.username})
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login/oauth", response_model=TokenResponse, include_in_schema=False)
async def login_oauth(form: OAuth2PasswordRequestForm = Depends(),
                      db: AsyncSession = Depends(get_db)):
    """Swagger UI Authorize 버튼용 (OAuth2PasswordRequestForm)."""
    body = UserLogin(identifier=form.username, password=form.password)
    return await login_json(body, db)  # type: ignore


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
