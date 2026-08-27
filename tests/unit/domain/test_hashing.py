import pytest
from relay_security.hashing import hash_password, hash_token, verify_password


def test_correct_password_verifies() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed)


def test_wrong_password_is_rejected() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert not verify_password("wrong-password", hashed)


def test_same_password_hashes_differently_each_time() -> None:
    """Salted: two hashes of the same password must differ, or a leaked
    hash table would reveal which accounts share a password."""
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


def test_password_over_72_bytes_is_rejected_not_truncated() -> None:
    """bcrypt silently truncates past 72 bytes; two different passwords
    sharing the same first 72 bytes must not be treated as equal."""
    with pytest.raises(ValueError, match="72-byte"):
        hash_password("x" * 73)


def test_token_hash_is_deterministic() -> None:
    """No salt: verifying a presented token means hashing it again and
    comparing — the same input must always produce the same digest."""
    assert hash_token("same-token") == hash_token("same-token")


def test_token_hash_differs_for_different_tokens() -> None:
    assert hash_token("token-a") != hash_token("token-b")
