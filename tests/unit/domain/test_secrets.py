from relay_security.secrets import (
    API_KEY_PREFIX,
    VISIBLE_PREFIX_LENGTH,
    generate_api_key,
    generate_url_token,
    visible_prefix,
)


def test_api_key_has_the_spec_format() -> None:
    key = generate_api_key()
    assert key.startswith(API_KEY_PREFIX)
    assert len(key) - len(API_KEY_PREFIX) == 24


def test_generated_api_keys_do_not_collide() -> None:
    keys = {generate_api_key() for _ in range(1000)}
    assert len(keys) == 1000


def test_visible_prefix_never_exposes_the_full_key() -> None:
    key = generate_api_key()
    prefix = visible_prefix(key)
    assert len(prefix) == VISIBLE_PREFIX_LENGTH
    assert prefix != key
    assert key.startswith(prefix)


def test_url_token_is_url_safe() -> None:
    token = generate_url_token()
    assert not any(c in token for c in "+/=")
