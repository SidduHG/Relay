from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str
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


settings = Settings()
