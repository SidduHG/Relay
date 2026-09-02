"""Signup and login orchestration.

Not in the plan's original file list — signup/login didn't fit
jwt.py (token mechanics, not user creation) or project_service.py (org
and project membership, not accounts), so this is new, genuinely
distinct orchestration: check a business rule, then coordinate a repo
call with a packages/security call. That's a service's job.

Both open a TenantUnitOfWork with no org_id at all — signup and login
touch only `users` and `refresh_tokens`, both global tables with no RLS
policy, and packages/db/unit_of_work.py's org_id is optional for
exactly this (a signup has no org to scope by yet).
"""

from relay_api.auth.jwt import TokenPair, issue_pair
from relay_db.models.user import User
from relay_db.unit_of_work import TenantUnitOfWork
from relay_security.hashing import hash_password, verify_password
from relay_security.validation import is_valid_email, is_valid_password, normalize_email


class InvalidEmailError(Exception):
    pass


class WeakPasswordError(Exception):
    pass


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Deliberately one error for both 'no such user' and 'wrong
    password' — same 404-vs-403 reasoning as tenancy.py: a distinct
    message for 'no such user' would let an attacker enumerate
    registered emails."""


# A fixed, precomputed bcrypt hash of a string that is not a real
# credential — used only so the "no such user" branch of login() pays
# the same bcrypt cost as the "wrong password" branch. Verified this
# matters directly: without it, "user not found" returns in ~0.002ms
# and "wrong password" takes ~210ms, a trivially measurable timing
# side-channel that lets an attacker enumerate registered emails even
# though both branches raise the identical InvalidCredentialsError.
_DUMMY_HASH = "$2b$12$SUKMcteWQbYJxsV8BYmj3O3xeT7KC4Laf3QgK5Now/rZIi3PGh4Ra"


async def signup(uow: TenantUnitOfWork, email: str, password: str) -> User:
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        raise InvalidEmailError(email)
    if not is_valid_password(password):
        raise WeakPasswordError("password does not meet the minimum length")
    if await uow.users.get_by_email(normalized) is not None:
        raise EmailAlreadyRegisteredError(normalized)
    return await uow.users.create(email=normalized, password_hash=hash_password(password))


async def login(
    uow: TenantUnitOfWork, email: str, password: str, *, secret_key: str
) -> TokenPair:
    user = await uow.users.get_by_email(normalize_email(email))
    hash_to_check = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = verify_password(password, hash_to_check)

    if user is None or not password_ok:
        raise InvalidCredentialsError()

    return await issue_pair(uow, user.id, secret_key=secret_key)
