from relay_security.validation import is_valid_email, is_valid_password, normalize_email


def test_normalize_email_lowercases_and_strips() -> None:
    assert normalize_email("  Sid@Acme.COM ") == "sid@acme.com"


def test_valid_email_accepted() -> None:
    assert is_valid_email("sid@acme.com")


def test_email_without_at_sign_rejected() -> None:
    assert not is_valid_email("not-an-email")


def test_password_under_the_floor_rejected() -> None:
    assert not is_valid_password("short")


def test_password_at_the_floor_accepted() -> None:
    assert is_valid_password("longenough1")
