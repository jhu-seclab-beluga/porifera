"""AST deinstrumentation: removing probe calls to restore original expressions.

Provides ASTDeinstrumenter for identifying and unwrapping probe function calls.
Identifies probes by __lemur_probe_ prefix matching.
"""

import logging
from pathlib import Path

from php_parser_py import AST, Modifier, Node, Parser, PrettyPrinter

from .._exceptions import DeinstrumentationError
from ._instrumenter import _PROBE_FUNC_PREFIX

logger = logging.getLogger(__name__)


class ASTDeinstrumenter:
    """Removes probe function calls by unwrapping to restore original expressions.

    Identifies probes by __lemur_probe_ prefix matching. No constructor params.
    """

    def unwrap_probe_ast(
        self,
        file_path: Path,
        expr_key: str,
        ast: AST,
        exclude_node_ids: set[str] | None = None,
    ) -> bool:
        """Find probe call matching expr_key and replace with original expression.

        Args:
            file_path: For error messages.
            expr_key: Probe label to match.
            ast: AST modified in place.
            exclude_node_ids: Node IDs to skip (already processed).

        Returns:
            True if found and replaced, False otherwise.

        Raises:
            DeinstrumentationError: If probe structure is invalid.
        """
        if exclude_node_ids is None:
            exclude_node_ids = set()

        call_node_id, original_expr_id = self._find_probe_call_by_expr_key(
            ast, expr_key, exclude_node_ids,
        )
        if call_node_id is None or original_expr_id is None:
            return False

        self._replace_call_with_expression(ast, call_node_id, original_expr_id, file_path)
        exclude_node_ids.add(call_node_id)
        return True

    def scan_and_unwrap(self, project_root: Path) -> list[Path]:
        """Scan all PHP files and unwrap probe calls.

        Args:
            project_root: Root directory to scan.

        Returns:
            List of modified file paths.

        Raises:
            DeinstrumentationError: On parse or write errors.
        """
        modified_files: list[Path] = []

        for php_file in project_root.rglob("*.php"):
            if self._process_php_file_for_unwrap(php_file):
                modified_files.append(php_file)

        return modified_files

    def _find_probe_call_by_expr_key(
        self,
        ast: AST,
        expr_key: str,
        exclude_node_ids: set[str],
    ) -> tuple[str | None, str | None]:
        """Find probe call node matching expr_key in first argument."""
        for node in ast.nodes():
            if node.id in exclude_node_ids:
                continue
            if node.node_type != "Expr_FuncCall":
                continue
            if not self._is_probe_call(ast, node):
                continue
            if self._get_probe_first_arg_value(ast, node) != expr_key:
                continue

            original_expr_id = self._get_probe_second_arg_expr(ast, node)
            if original_expr_id is not None:
                return node.id, original_expr_id

        return None, None

    def _is_probe_call(self, ast: AST, call_node: Node) -> bool:
        """Check if a FuncCall node is a probe call (by prefix match)."""
        for child in ast.succ(call_node):
            edge = ast.edge(call_node.id, child.id, "PARENT_OF")
            if not edge or edge.get("field") != "name":
                continue
            if child.node_type != "Name":
                return False
            parts: list[str] = child.get_property("parts") or []
            return (
                len(parts) == 1
                and isinstance(parts[0], str)
                and parts[0].startswith(_PROBE_FUNC_PREFIX)
            )
        return False

    def _get_probe_first_arg_value(self, ast: AST, call_node: Node) -> str | None:
        """Get the string value of the first argument."""
        arg_node = self._get_arg_by_index(ast, call_node, 0)
        if arg_node is None:
            return None

        for child in ast.succ(arg_node):
            edge = ast.edge(arg_node.id, child.id, "PARENT_OF")
            if not edge or edge.get("field") != "value":
                continue
            if child.node_type == "Scalar_String":
                return child.get_property("value")
        return None

    def _get_probe_second_arg_expr(self, ast: AST, call_node: Node) -> str | None:
        """Get the expression node ID from the second argument."""
        arg_node = self._get_arg_by_index(ast, call_node, 1)
        if arg_node is None:
            return None

        for child in ast.succ(arg_node):
            edge = ast.edge(arg_node.id, child.id, "PARENT_OF")
            if not edge or edge.get("field") != "value":
                continue
            return child.id
        return None

    def _get_arg_by_index(self, ast: AST, call_node: Node, index: int) -> Node | None:
        """Get argument node by index from a function call."""
        for child in ast.succ(call_node):
            edge = ast.edge(call_node.id, child.id, "PARENT_OF")
            if not edge:
                continue
            if edge.get("field") != "args" or edge.get("index") != index:
                continue
            if child.node_type == "Arg":
                return child
        return None

    def _replace_call_with_expression(
        self, ast: AST, call_node_id: str, expr_node_id: str, file_path: Path,
    ) -> None:
        """Replace probe call node with the original expression node."""
        modifier = Modifier(ast)

        call_node = ast.node(call_node_id)
        parents = list(ast.prev(call_node))
        if not parents:
            raise DeinstrumentationError(f"Orphaned probe call (no parent) in {file_path}")

        parent_node = parents[0]
        parent_edge = ast.edge(parent_node.id, call_node_id, "PARENT_OF")
        if not parent_edge:
            raise DeinstrumentationError(f"No PARENT_OF edge for probe call in {file_path}")

        saved_field = parent_edge.get("field")
        saved_index = parent_edge.get("index")

        modifier.remove_edge(parent_node.id, call_node_id)

        expr_node = ast.node(expr_node_id)
        for expr_parent in list(ast.prev(expr_node)):
            if expr_parent.id != parent_node.id:
                modifier.remove_edge(expr_parent.id, expr_node_id)

        if saved_index is not None:
            modifier.add_edge(
                parent_node.id, expr_node_id, field=saved_field, index=saved_index,
            )
        else:
            modifier.add_edge(parent_node.id, expr_node_id, field=saved_field)

    def _process_php_file_for_unwrap(self, php_file: Path) -> bool:
        """Process a single PHP file; return True if modified."""
        content = php_file.read_text(encoding="utf-8")
        if _PROBE_FUNC_PREFIX not in content:
            return False

        ast = Parser().parse_file(str(php_file))
        calls_to_replace = [
            node.id
            for node in ast.nodes()
            if node.node_type == "Expr_FuncCall" and self._is_probe_call(ast, node)
        ]
        if not calls_to_replace:
            return False

        for call_id in calls_to_replace:
            call_node = ast.node(call_id)
            second_arg_id = self._get_probe_second_arg_expr(ast, call_node)
            if second_arg_id is None:
                raise DeinstrumentationError(
                    f"Probe call without second argument in {php_file}",
                )
            self._replace_call_with_expression(ast, call_id, second_arg_id, php_file)

        result = PrettyPrinter().print(ast)
        if not result:
            raise DeinstrumentationError(f"PrettyPrinter produced no output for {php_file}")
        php_file.write_text(next(iter(result.values())), encoding="utf-8")
        return True
