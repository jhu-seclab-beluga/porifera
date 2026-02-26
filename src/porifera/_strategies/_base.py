"""Base probe strategy definitions and safety checks.

Provides _is_safe_to_wrap() for checking wrapping safety against lvalue/reference
contexts, and the ProbeStrategy ABC for injectable target selection.
"""

import logging
from abc import ABC, abstractmethod

from php_parser_py import AST, Node

logger = logging.getLogger(__name__)

_UNSAFE_WRAP_CONTEXTS: frozenset[tuple[str, str]] = frozenset(
    {
        # Category A: Lvalue contexts
        ("Expr_Assign", "var"),
        ("Expr_AssignRef", "var"),
        ("Expr_AssignOp_Plus", "var"),
        ("Expr_AssignOp_Minus", "var"),
        ("Expr_AssignOp_Mul", "var"),
        ("Expr_AssignOp_Div", "var"),
        ("Expr_AssignOp_Mod", "var"),
        ("Expr_AssignOp_Concat", "var"),
        ("Expr_AssignOp_BitwiseAnd", "var"),
        ("Expr_AssignOp_BitwiseOr", "var"),
        ("Expr_AssignOp_BitwiseXor", "var"),
        ("Expr_AssignOp_ShiftLeft", "var"),
        ("Expr_AssignOp_ShiftRight", "var"),
        ("Expr_AssignOp_Pow", "var"),
        ("Expr_AssignOp_Coalesce", "var"),
        ("Expr_PreInc", "var"),
        ("Expr_PostInc", "var"),
        ("Expr_PreDec", "var"),
        ("Expr_PostDec", "var"),
        ("Stmt_Foreach", "keyVar"),
        ("Stmt_Foreach", "valueVar"),
        ("Stmt_Unset", "vars"),
        # Category C: Reference contexts
        ("Expr_AssignRef", "expr"),
    }
)


def _is_safe_to_wrap(ast: AST, node: Node) -> bool:
    """Check if wrapping node in a probe call preserves semantics."""
    parents = list(ast.prev(node))
    if not parents:
        return False

    parent_node = parents[0]
    parent_edge = ast.edge(parent_node.id, node.id, "PARENT_OF")
    if not parent_edge:
        return False

    edge_field: str = parent_edge.get("field") or ""
    return (parent_node.node_type, edge_field) not in _UNSAFE_WRAP_CONTEXTS


class ProbeStrategy(ABC):
    """Selects which node to wrap. Pure decision logic — no AST mutation, no probe naming.

    Given a target node, returns the node that should be wrapped, or None if unable
    to instrument. The returned node may differ from the input (e.g. an ancestor).
    """

    @abstractmethod
    def select_wrap_target(
        self,
        ast: AST,
        node: Node,
        wrapped_node_ids: set[str],
    ) -> Node | None:
        """Return the node to wrap, or None if unable to instrument.

        Args:
            ast: Project AST.
            node: Target node to consider.
            wrapped_node_ids: IDs already wrapped — skip these.

        Returns:
            Node to wrap, or None.
        """
