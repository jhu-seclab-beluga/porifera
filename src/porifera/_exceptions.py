"""Exceptions for instrumentation operations."""


class InstrumentationError(Exception):
    """Raised during instrumentation (parse error, write failure, registry error)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DeinstrumentationError(InstrumentationError):
    """Raised during deinstrumentation (registry corrupted, AST parse error)."""
