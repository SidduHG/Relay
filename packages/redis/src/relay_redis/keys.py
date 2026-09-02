"""Every Redis key this project uses, named in one place. Nothing about
job streams, delay sets, or worker registries yet — those land with
F2/F3/F5/F7. Only the rate-limit keys Task 12 actually needs exist here
today; adding a new key pattern later is additive, not a rename of
these.
"""


def login_ip_rate_limit_key(ip: str) -> str:
    return f"ratelimit:login:ip:{ip}"


def login_email_rate_limit_key(email: str) -> str:
    return f"ratelimit:login:email:{email.strip().lower()}"


def api_key_failure_rate_limit_key(ip: str) -> str:
    return f"ratelimit:apikey:ip:{ip}"
