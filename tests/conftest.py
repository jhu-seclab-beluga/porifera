"""Shared test fixtures for lemur tests.

Provides helpers for creating real PHP files and parsing them with php-parser-py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from php_parser_py import AST, Node, Parser


def write_php(directory: Path, filename: str, code: str) -> Path:
    """Write PHP code to a file in the given directory.

    Args:
        directory: Directory to write the file in.
        filename: Name of the PHP file.
        code: PHP source code (should start with <?php).

    Returns:
        Path to the created file.
    """
    php_file = directory / filename
    php_file.write_text(code, encoding="utf-8")
    return php_file


def parse_php(directory: Path, filename: str = "test.php", code: str = "<?php\n") -> AST:
    """Write PHP code and parse it, returning the AST.

    Args:
        directory: Directory for the temp file.
        filename: Name of the PHP file.
        code: PHP source code.

    Returns:
        Parsed AST.
    """
    write_php(directory, filename, code)
    return Parser().parse_file(str(directory / filename))


def find_node(ast: AST, node_type: str, **props: object) -> Node:
    """Find the first node matching type and optional property values.

    Args:
        ast: Parsed AST.
        node_type: Node type to match (e.g. "Expr_Assign").
        **props: Optional property key-value pairs to match.

    Returns:
        The matching node.

    Raises:
        ValueError: If no matching node is found.
    """
    for node in ast.nodes():
        if node.node_type != node_type:
            continue
        if all(node.get_property(k) == v for k, v in props.items()):
            return node
    raise ValueError(f"No {node_type} node found with props {props}")


def find_nodes(ast: AST, node_type: str) -> list[Node]:
    """Find all nodes of a given type.

    Args:
        ast: Parsed AST.
        node_type: Node type to match.

    Returns:
        List of matching nodes.
    """
    return [n for n in ast.nodes() if n.node_type == node_type]


def find_child(ast: AST, parent: Node, field: str) -> Node | None:
    """Find a child node by edge field name.

    Args:
        ast: Parsed AST.
        parent: Parent node.
        field: Edge field to match.

    Returns:
        Child node, or None if not found.
    """
    return next(ast.succ(parent, lambda e: e.get("field") == field), None)


@pytest.fixture()
def php_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for PHP test files."""
    return tmp_path
