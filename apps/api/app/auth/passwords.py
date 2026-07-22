from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

SCHEME = "scrypt"
N = 2**14
R = 8
P = 1
DKLEN = 32
SALT_BYTES = 16
MAX_PASSWORD_BYTES = 512


def _password_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("密码过长")
    return encoded


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.scrypt(_password_bytes(password), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    return "$".join(
        (
            SCHEME,
            str(N),
            str(R),
            str(P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(derived).decode("ascii"),
        )
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        scheme, raw_n, raw_r, raw_p, raw_salt, raw_derived = stored_hash.split("$", 5)
        if scheme != SCHEME:
            return False
        n, r, p = int(raw_n), int(raw_r), int(raw_p)
        if (n, r, p) != (N, R, P):
            return False
        salt = base64.urlsafe_b64decode(raw_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(raw_derived.encode("ascii"))
        if len(salt) != SALT_BYTES or len(expected) != DKLEN:
            return False
        actual = hashlib.scrypt(
            _password_bytes(password), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
