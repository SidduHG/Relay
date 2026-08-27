from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    worker_id: str = "worker-1"
    worker_concurrency: int = 10
    log_level: str = "INFO"

    database_url: str
    redis_url: str


settings = Settings()
