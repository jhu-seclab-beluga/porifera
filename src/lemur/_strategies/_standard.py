"""Standard probe strategy: selects safe rvalue targets directly.

Returns the target node if it is safe to wrap, None otherwise.
Does not attempt elevation to ancestor nodes.
"""

from php_parser_py import AST, Node

from ._base import ProbeStrategy, _is_safe_to_wrap


class StandardProbeStrategy(ProbeStrategy):
    """Selects safe rvalue targets directly; returns None for unsafe targets."""

    def select_wrap_target(
        self, ast: AST, node: Node, wrapped_node_ids: set[str],
    ) -> Node | None:
        if node.id in wrapped_node_ids:
            return None
        if not _is_safe_to_wrap(ast, node):
            return None
        return node
