"""Generation of API keys and URL-safe tokens.

Everything here uses the stdlib `secrets` module, never `random`. `random`
is a Mersenne Twister: deterministic and reproducible from its internal
state, which makes it fine for simulations and wrong for anything security
sensitive — an attacker who recovers enough output can predict the rest.
`secrets` reads from the OS's cryptographically secure random source.
"""

import secrets
import string

API_KEY_PREFIX = "rly_live_"
_API_KEY_RANDOM_LENGTH = 24
_API_KEY_ALPHABET = string.ascii_letters + string.digits

# How much of a key stays visible in clear (api_keys.prefix in the DB) so
# the dashboard can show "which key is which" without ever storing or
# re-displaying the secret half. Long enough to distinguish keys at a
# glance, short enough that it is not itself a usable secret.
VISIBLE_PREFIX_LENGTH = 12


def generate_api_key() -> str:
    """Returns a full key like `rly_live_aB3xQ...` — 24 random characters
    after the prefix, per RELAY-SPEC.md F1."""
    random_part = "".join(
        secrets.choice(_API_KEY_ALPHABET) for _ in range(_API_KEY_RANDOM_LENGTH)
    )
    return f"{API_KEY_PREFIX}{random_part}"


def visible_prefix(api_key: str) -> str:
    """The portion stored in clear text. Never call this on the full key
    and store the result as if it were safe to also store the rest —
    only ever pair it with hash_token() of the complete key."""
    return api_key[:VISIBLE_PREFIX_LENGTH]


def generate_url_token() -> str:
    """A random token for links: invites and refresh tokens. 32 bytes of
    entropy, URL-safe base64 — safe to embed directly in an email link."""
    return secrets.token_urlsafe(32)
