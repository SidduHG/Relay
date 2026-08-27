from relay_observability.logging import configure_logging

from relay_api.config import settings


def setup_logging() -> None:
    configure_logging(settings.log_level)
