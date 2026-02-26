"""Tests for porifera._exceptions."""

from porifera._exceptions import DeinstrumentationError, InstrumentationError


def test_instrumentation_error_message_preserved():
    err = InstrumentationError("test message")
    assert str(err) == "test message"
    assert err.message == "test message"


def test_deinstrumentation_error_inherits_instrumentation_error():
    err = DeinstrumentationError("deinstrument failed")
    assert isinstance(err, InstrumentationError)
    assert isinstance(err, Exception)


def test_deinstrumentation_error_message_preserved():
    err = DeinstrumentationError("bad registry")
    assert str(err) == "bad registry"
    assert err.message == "bad registry"
