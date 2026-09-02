"""Maps every plain exception raised by the auth layer to an HTTP
status code, in one place.

Every module built across this branch — jwt.py, api_keys.py, rbac.py,
tenancy.py, auth_service.py, project_service.py — deliberately raises
plain Python exceptions instead of importing HTTPException, so the
auth-logic layer never has to know it's being called over HTTP. This is
where that decision cashes out: one registration loop, not a
try/except block repeated in every route.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from relay_api.auth.api_keys import InvalidApiKeyError
from relay_api.auth.jwt import (
    InvalidAccessTokenError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
)
from relay_api.auth.rbac import PermissionDeniedError
from relay_api.auth.tenancy import MissingCredentialsError, TenantNotFoundError
from relay_api.middleware.rate_limit import RateLimitExceededError
from relay_api.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidEmailError,
    WeakPasswordError,
)
from relay_api.services.project_service import (
    AlreadyAMemberError,
    EscalationError,
    InvitationEmailMismatchError,
    InvitationInvalidError,
    LastOwnerError,
    NotAMemberError,
    NotAnOrgMemberError,
)

# 401: we cannot tell who is making this request.
_UNAUTHORIZED: tuple[type[Exception], ...] = (
    MissingCredentialsError,
    InvalidAccessTokenError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    InvalidApiKeyError,
    InvalidCredentialsError,
)

# 403: we know who is asking; this specific action is not theirs to take.
_FORBIDDEN: tuple[type[Exception], ...] = (
    PermissionDeniedError,
    EscalationError,
    InvitationEmailMismatchError,
)

# 404: RELAY-SPEC.md F1 — another tenant's resource, or a membership
# that does not exist, must look identical to "this does not exist."
# A 403 here would itself leak that the resource exists.
_NOT_FOUND: tuple[type[Exception], ...] = (TenantNotFoundError, NotAMemberError)

# 400: the request is well-formed but violates a business rule that
# does not depend on any existing row's state.
_BAD_REQUEST: tuple[type[Exception], ...] = (
    InvalidEmailError,
    WeakPasswordError,
    NotAnOrgMemberError,
    InvitationInvalidError,
)

# 409: the request is valid but conflicts with the current state of a
# resource that already exists.
_CONFLICT: tuple[type[Exception], ...] = (
    EmailAlreadyRegisteredError,
    LastOwnerError,
    AlreadyAMemberError,
)

# 429: RELAY-SPEC.md's own general pattern for backpressure (F8 uses it
# for queue depth too) — reject, and the caller should back off.
_TOO_MANY_REQUESTS: tuple[type[Exception], ...] = (RateLimitExceededError,)

_STATUS_GROUPS: tuple[tuple[int, tuple[type[Exception], ...]], ...] = (
    (401, _UNAUTHORIZED),
    (403, _FORBIDDEN),
    (404, _NOT_FOUND),
    (400, _BAD_REQUEST),
    (409, _CONFLICT),
    (429, _TOO_MANY_REQUESTS),
)


def _make_handler(status_code: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def _handler(_request: Request, exc: Exception) -> JSONResponse:
        detail = str(exc) or exc.__class__.__name__
        return JSONResponse(status_code=status_code, content={"detail": detail})

    return _handler


def register_error_handlers(app: FastAPI) -> None:
    for status_code, exception_types in _STATUS_GROUPS:
        handler = _make_handler(status_code)
        for exc_type in exception_types:
            app.add_exception_handler(exc_type, handler)
