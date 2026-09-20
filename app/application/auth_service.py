"""Registration and login. Pure business logic over the ports."""

from app.application.ports import Clock, PasswordHasher, TokenService, UnitOfWork
from app.domain.enums import UserRole
from app.domain.errors import ConflictError, UnauthorizedError, ValidationError
from app.domain.models import User

MIN_PASSWORD_LENGTH = 8


class AuthService:
    def __init__(
        self,
        uow: UnitOfWork,
        hasher: PasswordHasher,
        tokens: TokenService,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock

    def register(
        self, email: str, password: str, full_name: str, role: UserRole = UserRole.USER
    ) -> User:
        email = (email or "").strip().lower()
        if not email:
            raise ValidationError("email must not be blank")
        if not (full_name or "").strip():
            raise ValidationError("full_name must not be blank")
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters long"
            )
        # Self-signup as ADMIN is never allowed; admins are provisioned out of band.
        if role == UserRole.ADMIN:
            raise ValidationError("cannot self-register as ADMIN")

        with self._uow as uow:
            if uow.users.exists_by_email(email):
                raise ConflictError("email is already registered")
            user = uow.users.add(
                User(
                    email=email,
                    password_hash=self._hasher.hash(password),
                    full_name=full_name.strip(),
                    role=role,
                    created_at=self._clock.now(),
                )
            )
            uow.commit()
            return user

    def login(self, email: str, password: str) -> tuple[User, str, int]:
        """Return ``(user, access_token, expires_in_seconds)``."""
        email = (email or "").strip().lower()
        with self._uow as uow:
            user = uow.users.get_by_email(email)
            # Same error for unknown email and wrong password: do not leak which
            # addresses are registered.
            if user is None or not self._hasher.verify(password or "", user.password_hash):
                raise UnauthorizedError("invalid email or password", code="INVALID_CREDENTIALS")
            token, expires_in = self._tokens.issue(user)
            return user, token, expires_in

    def get_profile(self, user_id: int) -> User:
        with self._uow as uow:
            user = uow.users.get_by_id(user_id)
            if user is None:
                # The token was signed by us but the user is gone.
                raise UnauthorizedError("account no longer exists", code="INVALID_CREDENTIALS")
            return user
