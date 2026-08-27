import contextvars
import json
import logging
import sys
import time

_context: contextvars.ContextVar[dict] = contextvars.ContextVar("log_context", default={})

_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = {
            k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS
        }
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **_context.get(),
            **extras,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def bind_context(**fields: object) -> None:
    current = dict(_context.get())
    current.update(fields)
    _context.set(current)


def clear_context() -> None:
    _context.set({})
