"""Tests for porifera._exceptions."""

from porifera._exceptions import DeinstrumentationError, InstrumentationError


def test_instrumentation_error_message_preserved():
    """InstrumentationError stores and exposes message."""
    err = InstrumentationError("test message")
    assert str(err) == "test message"
    assert err.message == "test message"


def test_deinstrumentation_error_inherits_instrumentation_error():
    """DeinstrumentationError is a subclass of InstrumentationError."""
    err = DeinstrumentationError("deinstrument failed")
    assert isinstance(err, InstrumentationError)
    assert isinstance(err, Exception)


def test_deinstrumentation_error_message_preserved():
    """DeinstrumentationError stores and exposes message."""
    err = DeinstrumentationError("bad registry")
    assert str(err) == "bad registry"
    assert err.message == "bad registry"
