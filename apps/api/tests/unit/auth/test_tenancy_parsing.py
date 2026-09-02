"""parse_bearer_token needs nothing but strings — pure, unit-testable."""

import pytest
from relay_api.auth.tenancy import MissingCredentialsError, parse_bearer_token


def test_missing_header_is_rejected() -> None:
    with pytest.raises(MissingCredentialsError):
        parse_bearer_token(None)


def test_wrong_scheme_is_rejected() -> None:
    with pytest.raises(MissingCredentialsError):
        parse_bearer_token("Basic dXNlcjpwYXNz")


def test_missing_token_after_scheme_is_rejected() -> None:
    with pytest.raises(MissingCredentialsError):
        parse_bearer_token("Bearer")


def test_valid_header_returns_the_token() -> None:
    assert parse_bearer_token("Bearer abc123") == "abc123"


def test_extra_whitespace_around_the_token_is_stripped() -> None:
    """A double space is an easy copy-paste artifact — must not leak
    into the token and cause a confusing signature/hash mismatch
    instead of a clean parse failure."""
    assert parse_bearer_token("Bearer  abc123  ") == "abc123"


def test_scheme_check_is_case_insensitive() -> None:
    assert parse_bearer_token("bearer abc123") == "abc123"
