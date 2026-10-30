"""Parola, oturum belirteci, TOTP, alan şifreleme ve takip kodu yardımcıları."""
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_ph = PasswordHasher()

# Karıştırılabilecek karakterler (0/O, 1/I/L) çıkarılmış alfabe: 31 karakter.
_TRACK_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_TRACK_LEN = 12  # ~59 bit


# --- Parola -----------------------------------------------------------------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


# Kullanıcı bulunamadığında da aynı süreyi harcamak için (kullanıcı adı tahminini zorlaştırır)
_DUMMY_HASH = _ph.hash("timing-equalizer")


def burn_password_check(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


# --- Alan şifreleme -----------------------------------------------------------
@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().field_encryption_key.encode())


def enc(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return _fernet().encrypt(value.encode()).decode()


def dec(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return "[çözülemedi]"


# --- Takip kodu --------------------------------------------------------------
def new_tracking_code() -> str:
    raw = "".join(secrets.choice(_TRACK_ALPHABET) for _ in range(_TRACK_LEN))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def normalize_tracking_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def tracking_code_hash(code: str) -> str:
    key = get_settings().tracking_pepper.encode()
    return hmac.new(key, normalize_tracking_code(code).encode(), hashlib.sha256).hexdigest()


# --- JWT -----------------------------------------------------------------------
def _encode(claims: dict, minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def staff_access_token(user_id: UUID, tenant_id: UUID, token_version: int) -> str:
    s = get_settings()
    return _encode(
        {"sub": str(user_id), "tid": str(tenant_id), "tv": token_version, "scope": "staff"},
        s.staff_token_minutes,
    )


def mfa_token(user_id: UUID, tenant_id: UUID, token_version: int, setup: bool) -> str:
    s = get_settings()
    return _encode(
        {
            "sub": str(user_id),
            "tid": str(tenant_id),
            "tv": token_version,
            "scope": "mfa_setup" if setup else "mfa",
        },
        s.mfa_token_minutes,
    )


def applicant_token(case_id: UUID, tenant_id: UUID) -> str:
    s = get_settings()
    return _encode({"sub": str(case_id), "tid": str(tenant_id), "scope": "applicant"}, s.applicant_token_minutes)


# --- TOTP ----------------------------------------------------------------------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def verify_totp(secret: str, code: str, last_step: int | None) -> int | None:
    """Kod geçerliyse kullanılan zaman adımını döndürür; aynı adım tekrar kullanılamaz."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    now_step = int(time.time()) // totp.interval
    for step in (now_step - 1, now_step, now_step + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            if last_step is not None and step <= last_step:
                return None
            return step
    return None
