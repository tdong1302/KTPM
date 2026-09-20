"""PasswordHasher adapter backed by bcrypt."""

import bcrypt


class BcryptPasswordHasher:
    def __init__(self, rounds: int = 12) -> None:
        self._rounds = rounds

    def hash(self, raw_password: str) -> str:
        salt = bcrypt.gensalt(rounds=self._rounds)
        return bcrypt.hashpw(raw_password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, raw_password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(
                raw_password.encode("utf-8"), password_hash.encode("utf-8")
            )
        except (ValueError, TypeError):
            # Malformed stored hash: treat as a failed login rather than a 500.
            return False
