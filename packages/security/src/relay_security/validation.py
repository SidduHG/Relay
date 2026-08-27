"""Input validation for the fields auth actually trusts.

Deliberately minimal — this is not a general-purpose validation library,
it's the two checks F1 needs before a password or email reaches hashing
or storage.
"""

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A floor, not a full policy. Real strength scoring (dictionary checks,
# breach-list lookups) is a v2 concern; this just stops "a" from being
# accepted as a password.
MIN_PASSWORD_LENGTH = 8


def normalize_email(email: str) -> str:
    """Lowercase and stripped, so `Sid@Acme.com` and `sid@acme.com ` are
    recognised as the same address at signup, invite, and login alike."""
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def is_valid_password(password: str) -> bool:
    return len(password) >= MIN_PASSWORD_LENGTH
