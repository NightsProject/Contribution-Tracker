import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("not-a-real-user-password")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024


def valid_email(email: str) -> bool:
    if len(email) > 320 or email.count("@") != 1 or any(char.isspace() for char in email):
        return False
    local, domain = email.split("@")
    return bool(local and "." in domain and not domain.startswith(".") and not domain.endswith("."))


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return PASSWORD_HASHER.check_needs_rehash(password_hash)


def new_session_id() -> str:
    return secrets.token_hex(32)


def hash_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("ascii")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def login_attempt_key(email: str, remote_address: str) -> str:
    return hashlib.sha256(f"{email}\0{remote_address}".encode("utf-8")).hexdigest()
