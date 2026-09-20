"""TokenService adapter backed by PyJWT (HS256)."""

from datetime import datetime, timedelta, timezone

import jwt

from app.application.ports import TokenClaims
from app.domain.enums import UserRole
from app.domain.errors import UnauthorizedError
from app.domain.models import User


class JwtTokenService:
    def __init__(self, secret: str, algorithm: str = "HS256", expires_minutes: int = 1440) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._expires_minutes = expires_minutes

    def issue(self, user: User) -> tuple[str, int]:
        now = datetime.now(timezone.utc)
        expires_in = self._expires_minutes * 60
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._expires_minutes)).timestamp()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, expires_in

    def verify(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
            return TokenClaims(
                user_id=int(payload["sub"]),
                email=payload["email"],
                role=UserRole(payload["role"]),
            )
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("access token has expired", code="TOKEN_EXPIRED") from exc
        except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
            raise UnauthorizedError("access token is invalid", code="TOKEN_INVALID") from exc
