"""Authentication endpoints."""

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.api.schemas.common import ErrorResponse
from app.domain.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        created_at=user.created_at,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account (public)",
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}},
)
def register(payload: RegisterRequest, service: AuthServiceDep) -> UserResponse:
    user = service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )
    return to_user_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Exchange credentials for an access token (public)",
    responses={401: {"model": ErrorResponse, "description": "Invalid credentials"}},
)
def login(payload: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    user, token, expires_in = service.login(email=payload.email, password=payload.password)
    return TokenResponse(access_token=token, expires_in=expires_in, user=to_user_response(user))


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current account (requires authentication)",
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid token"}},
)
def me(principal: CurrentUser, service: AuthServiceDep) -> UserResponse:
    return to_user_response(service.get_profile(principal.user_id))
