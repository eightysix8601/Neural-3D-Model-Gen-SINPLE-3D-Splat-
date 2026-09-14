from __future__ import annotations
import uuid, re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator


USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{3,30}$")


class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("사용자명은 영문/숫자/_/- 만 3~30자")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 최소 8자")
        # 너무 약한 패턴만 거부 — 사용자 친화적으로
        if v.lower() in {"12345678", "password", "qwerty123"}:
            raise ValueError("너무 단순한 비밀번호입니다")
        return v


class UserLogin(BaseModel):
    """이메일 또는 username 으로 로그인 가능"""
    identifier: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    username: str
    is_admin: bool = False
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
