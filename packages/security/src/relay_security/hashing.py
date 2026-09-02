"""Two different hash functions for two different kinds of secret.

Passwords are low-entropy and human-chosen ("password123" is a real
password people use) — an attacker with a stolen hash can try billions of
guesses per second on fast hardware. Password hashing must therefore be
*deliberately slow*, so bcrypt is used, with its cost tunable as hardware
gets faster.

API keys and tokens are high-entropy and machine-generated (24+ random
characters from secrets.py). A slow hash buys nothing here — brute force
is already infeasible — and would only slow down every single request's
auth check. sha256 is used instead: fast, deterministic, one-way.

Never swap these: bcrypt on a token wastes CPU on every request for zero
security benefit; sha256 on a password is crackable at billions of
guesses per second on commodity GPUs.
"""

import hashlib

import bcrypt

# bcrypt silently truncates any input past 72 bytes and hashes only the
# first 72 — two different 200-character passwords sharing the same first
# 72 bytes would hash identically. Reject rather than silently truncate.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"password exceeds bcrypt's {_BCRYPT_MAX_BYTES}-byte limit; "
            "silently truncating would let differing passwords hash identically"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode("ascii"))


def hash_token(token: str) -> str:
    """Hash an API key or refresh/invite token for storage.

    Deterministic on purpose: verifying a presented token means hashing it
    again and comparing to the stored hash — there is no "check" function
    the way bcrypt has one, because there is no salt to look up first.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
