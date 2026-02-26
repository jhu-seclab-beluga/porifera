"""PORIFERA: PHP AST instrumentation module.

Exports public API functions and strategy classes for PHP AST instrumentation.
"""

from ._exceptions import DeinstrumentationError, InstrumentationError
from ._manager import deinstrument, instrument
from ._strategies import ElevatingProbeStrategy, ProbeStrategy, StandardProbeStrategy

__all__ = [
    "instrument",
    "deinstrument",
    "InstrumentationError",
    "DeinstrumentationError",
    "ProbeStrategy",
    "StandardProbeStrategy",
    "ElevatingProbeStrategy",
]
