"""Auth request and response DTOs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.domain.enums import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=150)
    # ADMIN is intentionally absent: it is rejected by the business layer anyway, and
    # leaving it out keeps it off the public API surface.
    role: Literal[UserRole.USER, UserRole.ORGANIZER] = UserRole.USER


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
