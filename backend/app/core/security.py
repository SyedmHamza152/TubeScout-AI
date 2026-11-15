"""Security helpers: password hashing (PBKDF2), JWT, Fernet token encryption.

OAuth refresh tokens for Google connections are encrypted at rest and never
returned to the frontend.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

import jwt
from cryptography.fernet import Fernet

from app.core.config import settings

_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(digest.hex(), expected)
    except Exception:
        return False


def create_access_token(user_id: str, workspace_id: str | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + settings.JWT_EXPIRE_MINUTES * 60,
        "jti": secrets.token_hex(8),
    }
    if workspace_id:
        payload["ws"] = workspace_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except Exception:
        return ""


def new_api_state() -> str:
    return secrets.token_urlsafe(24)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def random_password() -> str:
    return secrets.token_urlsafe(18) + os.urandom(2).hex()
