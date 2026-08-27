import logging
import signal
import time

from relay_worker.config import settings
from relay_worker.logging import setup_logging

setup_logging()
logger = logging.getLogger("relay_worker")

_shutdown = False


def _handle_sigterm(*_args: object) -> None:
    global _shutdown
    logger.info("shutdown signal received", extra={"worker_id": settings.worker_id})
    _shutdown = True


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    logger.info("worker starting", extra={"worker_id": settings.worker_id})

    # Fetch loop, claim/lease, and execution land in F3.
    while not _shutdown:
        time.sleep(1)

    logger.info("worker stopped", extra={"worker_id": settings.worker_id})


if __name__ == "__main__":
    main()
