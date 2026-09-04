from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # 32 bytes is HS256's own recommended floor (RFC 7518 §3.2) — PyJWT
    # warns at import time below it. Enforced here instead of discovered
    # via a runtime warning: a short secret should fail loudly on boot,
    # matching F0's rule for any other missing/invalid config.
    api_secret_key: str = Field(min_length=32)
    api_env: str = "development"
    log_level: str = "INFO"

    database_url: str
    # Used only at startup, for bootstrap (see lifecycle.py). Bootstrap
    # runs before any organization exists, so it cannot use the RLS-
    # restricted database_url connection — organizations' policy is
    # self-referential (id = current_setting('app.org_id')), which makes
    # "does any org exist yet" undiscoverable without already knowing an
    # id to scope by. Verified directly: the RLS-restricted role could
    # create the first org but then could never find it again.
    database_admin_url: str
    redis_url: str

    default_org_name: str = "Default"
    default_org_slug: str = "default"

    blob_store_url: str = "file:///var/lib/relay/payloads"
    payload_inline_max_bytes: int = Field(default=262_144, gt=0)
    payload_max_bytes: int = Field(default=10_485_760, gt=0)
    blob_upload_timeout_seconds: int = Field(default=10, gt=0)
    idempotency_window_hours: int = Field(default=24, gt=0)
    queue_stream_maxlen: int = Field(default=100_000, gt=0)
    queue_config_cache_seconds: int = Field(default=5, gt=0)
    enqueue_redis_retry_attempts: int = Field(default=3, ge=0, le=10)
    job_list_page_size_default: int = Field(default=50, ge=1, le=200)
    job_list_page_size_max: int = Field(default=200, ge=1, le=200)
    purge_token_ttl_seconds: int = Field(default=300, gt=0)
    jobs_partition_months_ahead: int = Field(default=3, ge=1, le=24)

    @model_validator(mode="after")
    def validate_payload_limits(self) -> "Settings":
        if self.payload_inline_max_bytes >= self.payload_max_bytes:
            raise ValueError("payload_inline_max_bytes must be less than payload_max_bytes")
        if self.job_list_page_size_default > self.job_list_page_size_max:
            raise ValueError("default page size must not exceed maximum page size")
        return self


settings = Settings()
