"""Domain-level errors.

These carry a stable machine-readable ``code`` so the API layer can map them to HTTP
status codes without the business layer knowing anything about HTTP.
"""


class DomainError(Exception):
    """Base class for every expected business rule violation."""

    code = "DOMAIN_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class ValidationError(DomainError):
    """Input violates a business rule. Maps to 400."""

    code = "VALIDATION_ERROR"


class NotFoundError(DomainError):
    """Requested aggregate does not exist (or must not be revealed). Maps to 404."""

    code = "NOT_FOUND"


class ConflictError(DomainError):
    """Action conflicts with current state, e.g. an illegal status transition. Maps to 409."""

    code = "CONFLICT"


class ForbiddenError(DomainError):
    """Caller is authenticated but not allowed to perform the action. Maps to 403."""

    code = "FORBIDDEN"


class UnauthorizedError(DomainError):
    """Caller could not be identified, e.g. bad credentials. Maps to 401."""

    code = "UNAUTHORIZED"
