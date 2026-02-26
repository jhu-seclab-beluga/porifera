"""Probe wrapping strategies for target selection.

Provides injectable ProbeStrategy ABC for configurable target selection,
StandardProbeStrategy for safe rvalue targets, and ElevatingProbeStrategy
for elevating unsafe targets to wrappable ancestors.
"""

from ._base import _UNSAFE_WRAP_CONTEXTS, ProbeStrategy, _is_safe_to_wrap
from ._elevating import ElevatingProbeStrategy
from ._standard import StandardProbeStrategy

__all__ = [
    "ProbeStrategy",
    "StandardProbeStrategy",
    "ElevatingProbeStrategy",
    "_is_safe_to_wrap",
    "_UNSAFE_WRAP_CONTEXTS",
]
