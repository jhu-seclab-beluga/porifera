"""AST instrumentation and deinstrumentation operations.

Provides ASTInstrumenter for wrapping expressions with probe calls,
and ASTDeinstrumenter for removing them to restore originals.
"""

from ._deinstrumenter import ASTDeinstrumenter
from ._instrumenter import ASTInstrumenter, _PROBE_FUNC_PREFIX

__all__ = [
    "ASTInstrumenter",
    "ASTDeinstrumenter",
    "_PROBE_FUNC_PREFIX",
]
