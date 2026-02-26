"""AST instrumentation: wrapping expressions with probe function calls.

Provides ASTInstrumenter for wrapping target expressions with probe calls.
Uses ProbeStrategy for target selection; tracks wrapped nodes to prevent
double-wrapping.
"""

import logging
import uuid

from php_parser_py import AST, Modifier, Node

from .._exceptions import InstrumentationError
from .._strategies import ProbeStrategy

logger = logging.getLogger(__name__)

_PROBE_FUNC_PREFIX = "__porifera_probe_"


class ASTInstrumenter:
    """Owns probe naming and wrapping logic. Uses ProbeStrategy for target selection.

    Tracks wrapped node IDs to prevent double-wrapping when multiple targets
    elevate to the same ancestor.

    Attributes:
        _probe_func_name: Auto-generated probe function name (from Manager).
    """

    def __init__(
        self, project_ast: AST, strategy: ProbeStrategy, probe_func_name: str
    ) -> None:
        self._ast = project_ast
        self._modifier = Modifier(project_ast)
        self._strategy = strategy
        self._probe_func_name = probe_func_name
        self._wrapped_nodes: set[str] = set()

    def instrument_node(self, node_id: str, expr_key: str) -> bool:
        """Instrument a single node.

        Args:
            node_id: ID of the target node in the AST.
            expr_key: Probe label for the instrumented expression.

        Returns:
            True if the node was wrapped, False if skipped.

        Raises:
            InstrumentationError: On AST manipulation errors.
            KeyError: If node_id not found in AST.
        """
        node = self._ast.node(node_id)
        target = self._strategy.select_wrap_target(self._ast, node, self._wrapped_nodes)
        if target is None:
            logger.warning(
                "Skipping '%s' (node %s): no safe wrap target", expr_key, node_id
            )
            return False

        self._wrap_node(target, expr_key)
        self._wrapped_nodes.add(target.id)
        return True

    def _wrap_node(self, node: Node, expr_key: str) -> None:
        """Create probe Expr_FuncCall and re-parent target node under it."""
        func_call_id = f"probe_func_{uuid.uuid4().hex[:8]}"
        name_id = f"probe_name_{uuid.uuid4().hex[:8]}"
        arg1_id = f"probe_arg1_{uuid.uuid4().hex[:8]}"
        arg2_id = f"probe_arg2_{uuid.uuid4().hex[:8]}"
        str_id = f"probe_str_{uuid.uuid4().hex[:8]}"

        line_props = {"startLine": node.start_line, "endLine": node.end_line}

        self._create_probe_nodes(
            name_id,
            str_id,
            arg1_id,
            arg2_id,
            func_call_id,
            expr_key,
            line_props,
        )
        self._reparent_target(node, arg2_id, func_call_id)

    def _create_probe_nodes(
        self,
        name_id: str,
        str_id: str,
        arg1_id: str,
        arg2_id: str,
        func_call_id: str,
        expr_key: str,
        line_props: dict[str, int],
    ) -> None:
        """Create all probe AST nodes: Name, Scalar_String, Args, Expr_FuncCall."""
        self._modifier.add_node(
            name_id,
            "Name",
            parts=[self._probe_func_name],
            **line_props,
        )
        self._modifier.add_node(
            str_id,
            "Scalar_String",
            value=expr_key,
            **line_props,
        )

        self._modifier.add_node(
            arg1_id,
            "Arg",
            byRef=False,
            unpack=False,
            **line_props,
        )
        self._modifier.add_edge(arg1_id, str_id, field="value")

        self._modifier.add_node(
            arg2_id,
            "Arg",
            byRef=False,
            unpack=False,
            **line_props,
        )

        self._modifier.add_node(func_call_id, "Expr_FuncCall", **line_props)
        self._modifier.add_edge(func_call_id, name_id, field="name")
        self._modifier.add_edge(func_call_id, arg1_id, field="args", index=0)
        self._modifier.add_edge(func_call_id, arg2_id, field="args", index=1)

    def _reparent_target(self, node: Node, arg2_id: str, func_call_id: str) -> None:
        """Re-parent: detach from parent, attach under arg2, place FuncCall in original position."""
        parents = list(self._ast.prev(node))
        if not parents:
            raise InstrumentationError(f"Node {node.id} has no parent edge")
        parent_node = parents[0]
        parent_edge = self._ast.edge(parent_node.id, node.id, "PARENT_OF")
        if not parent_edge:
            raise InstrumentationError(f"Node {node.id} has no PARENT_OF edge")

        saved_field = parent_edge.get("field")
        saved_index = parent_edge.get("index")

        self._modifier.remove_edge(parent_node.id, node.id)

        self._modifier.add_edge(arg2_id, node.id, field="value")

        if saved_index is not None:
            self._modifier.add_edge(
                parent_node.id,
                func_call_id,
                field=saved_field,
                index=saved_index,
            )
        else:
            self._modifier.add_edge(parent_node.id, func_call_id, field=saved_field)
