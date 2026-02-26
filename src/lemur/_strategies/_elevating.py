"""Elevating probe strategy: walks up to nearest wrappable Expr_* ancestor.

For unsafe targets, walks parent chain via ast.prev() until hitting a non-Expr_*
node (statement boundary). Returns the first ancestor where _is_safe_to_wrap()
is True.
"""

from php_parser_py import AST, Node

from ._base import ProbeStrategy, _is_safe_to_wrap


class ElevatingProbeStrategy(ProbeStrategy):
    """For unsafe targets, walks up to the nearest wrappable Expr_* ancestor.

    Walks parent chain via ast.prev() until hitting a non-Expr_* node (statement
    boundary). Returns the first ancestor where _is_safe_to_wrap() is True.
    """

    def select_wrap_target(
        self,
        ast: AST,
        node: Node,
        wrapped_node_ids: set[str],
    ) -> Node | None:
        if node.id in wrapped_node_ids:
            return None

        if _is_safe_to_wrap(ast, node):
            return node

        ancestor = self._find_wrappable_ancestor(ast, node)
        if ancestor is not None and ancestor.id not in wrapped_node_ids:
            return ancestor
        return None

    def _find_wrappable_ancestor(self, ast: AST, node: Node) -> Node | None:
        """Walk up via ast.prev() until non-Expr_* boundary; return first safe Expr_* ancestor."""
        current = node
        while True:
            parents = list(ast.prev(current))
            if not parents:
                return None
            parent = parents[0]
            if not parent.node_type.startswith("Expr_"):
                return None
            if _is_safe_to_wrap(ast, parent):
                return parent
            current = parent
