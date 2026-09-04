class JobNotFoundError(LookupError):
    pass


class QueueNotFoundError(LookupError):
    pass


class SchemaValidationError(ValueError):
    pass


class InvalidQueueDefaultsError(ValueError):
    pass


class PurgeTokenInvalidError(ValueError):
    pass


class QueueIndexUnavailableError(RuntimeError):
    pass


class DatabaseUnavailableError(RuntimeError):
    pass
