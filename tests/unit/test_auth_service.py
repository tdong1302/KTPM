"""Registration and login rules."""

import pytest

from app.application.auth_service import AuthService
from app.domain.enums import UserRole
from app.domain.errors import ConflictError, UnauthorizedError, ValidationError
from tests.unit.fakes import FakeClock, FakeHasher, FakeTokenService, FakeUnitOfWork

VALID_PASSWORD = "correct-horse"


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def tokens() -> FakeTokenService:
    return FakeTokenService()


@pytest.fixture
def service(uow: FakeUnitOfWork, tokens: FakeTokenService) -> AuthService:
    return AuthService(uow, FakeHasher(), tokens, FakeClock())


class TestRegister:
    def test_registers_a_user_with_a_hashed_password(self, service):
        user = service.register("Alice@Example.com ", VALID_PASSWORD, "Alice")

        assert user.id is not None
        assert user.role == UserRole.USER
        assert user.password_hash != VALID_PASSWORD

    def test_email_is_normalised(self, service):
        assert service.register("Alice@Example.COM", VALID_PASSWORD, "Alice").email == (
            "alice@example.com"
        )

    def test_can_register_as_organizer(self, service):
        user = service.register("bob@example.com", VALID_PASSWORD, "Bob", UserRole.ORGANIZER)
        assert user.role == UserRole.ORGANIZER

    def test_cannot_self_register_as_admin(self, service):
        with pytest.raises(ValidationError):
            service.register("root@example.com", VALID_PASSWORD, "Root", UserRole.ADMIN)

    def test_duplicate_email_conflicts_regardless_of_case(self, service):
        service.register("alice@example.com", VALID_PASSWORD, "Alice")
        with pytest.raises(ConflictError):
            service.register("ALICE@example.com", VALID_PASSWORD, "Alice Again")

    @pytest.mark.parametrize("password", ["", "short"])
    def test_weak_password_is_rejected(self, service, password):
        with pytest.raises(ValidationError):
            service.register("alice@example.com", password, "Alice")

    def test_blank_full_name_is_rejected(self, service):
        with pytest.raises(ValidationError):
            service.register("alice@example.com", VALID_PASSWORD, "   ")

    def test_blank_email_is_rejected(self, service):
        with pytest.raises(ValidationError):
            service.register("  ", VALID_PASSWORD, "Alice")


class TestLogin:
    def test_successful_login_issues_a_token(self, service):
        registered = service.register("alice@example.com", VALID_PASSWORD, "Alice")

        user, token, expires_in = service.login("alice@example.com", VALID_PASSWORD)

        assert user.id == registered.id
        assert token
        assert expires_in > 0

    def test_login_is_case_insensitive_on_email(self, service):
        service.register("alice@example.com", VALID_PASSWORD, "Alice")
        _, token, _ = service.login("ALICE@EXAMPLE.COM", VALID_PASSWORD)
        assert token

    def test_wrong_password_is_rejected(self, service):
        service.register("alice@example.com", VALID_PASSWORD, "Alice")
        with pytest.raises(UnauthorizedError):
            service.login("alice@example.com", "wrong-password")

    def test_unknown_email_gives_the_same_error_as_a_wrong_password(self, service):
        """Do not let callers enumerate which addresses are registered."""
        service.register("alice@example.com", VALID_PASSWORD, "Alice")

        with pytest.raises(UnauthorizedError) as unknown:
            service.login("nobody@example.com", VALID_PASSWORD)
        with pytest.raises(UnauthorizedError) as wrong:
            service.login("alice@example.com", "wrong-password")

        assert unknown.value.code == wrong.value.code == "INVALID_CREDENTIALS"
        assert str(unknown.value) == str(wrong.value)

    def test_issued_token_carries_the_role(self, service, tokens):
        service.register("bob@example.com", VALID_PASSWORD, "Bob", UserRole.ORGANIZER)
        _, token, _ = service.login("bob@example.com", VALID_PASSWORD)
        assert tokens.verify(token).role == UserRole.ORGANIZER


class TestProfile:
    def test_returns_the_current_account(self, service):
        registered = service.register("alice@example.com", VALID_PASSWORD, "Alice")
        assert service.get_profile(registered.id).email == "alice@example.com"

    def test_deleted_account_is_unauthorized(self, service):
        with pytest.raises(UnauthorizedError):
            service.get_profile(4242)
