"""Job transition failures."""


class IllegalTransitionError(ValueError):
    pass


class StaleTransitionError(RuntimeError):
    pass
