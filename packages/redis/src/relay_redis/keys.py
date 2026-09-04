"""Every Redis key this project currently owns, named in one place."""

from uuid import UUID


def login_ip_rate_limit_key(ip: str) -> str:
    return f"ratelimit:login:ip:{ip}"


def login_email_rate_limit_key(email: str) -> str:
    return f"ratelimit:login:email:{email.strip().lower()}"


def api_key_failure_rate_limit_key(ip: str) -> str:
    return f"ratelimit:apikey:ip:{ip}"


def queue_stream_key(project_id: UUID, queue: str, priority: int) -> str:
    if priority not in range(4):
        raise ValueError("priority must be between 0 and 3")
    return f"q:{project_id}:{queue}:p{priority}"


def queue_paused_key(project_id: UUID, queue: str) -> str:
    return f"q:{project_id}:{queue}:paused"


def queue_config_key(project_id: UUID, queue: str) -> str:
    return f"queue:cfg:{project_id}:{queue}"


def purge_token_key(project_id: UUID, queue: str) -> str:
    return f"purge:token:{project_id}:{queue}"
