"""Password hashing behind one domain boundary."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from streambuild.auth.constants import PASSWORD_MIN_LENGTH
from streambuild.auth.exceptions import PasswordValidationError

_HASHER: PasswordHasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash one validated password with Argon2id."""

    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordValidationError(
            f"Password must contain at least {PASSWORD_MIN_LENGTH} characters"
        )
    return _HASHER.hash(password)


def verify_password(*, password_hash: str, password: str) -> tuple[bool, str | None]:
    """Verify a password and return a strengthened replacement hash when needed."""

    try:
        valid: bool = _HASHER.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False, None
    if not valid:
        return False, None
    return True, _HASHER.hash(password) if _HASHER.check_needs_rehash(password_hash) else None
