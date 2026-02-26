"""Tests for lemur._deinstrumenter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conftest import FakeAST, FakeModifier, FakeNode, build_parent_child
from lemur._operations._deinstrumenter import ASTDeinstrumenter
from lemur._exceptions import DeinstrumentationError


def _build_probe_call_ast(expr_key: str = "total") -> FakeAST:
    """Build an AST with a probe call: __lemur_probe_xxx("total", $original)."""
    ast = FakeAST()

    # Parent statement
    echo = FakeNode("echo1", "Stmt_Echo")

    # Probe Expr_FuncCall
    func_call = FakeNode("call1", "Expr_FuncCall", startLine=1, endLine=1)

    # Name node
    name = FakeNode("name1", "Name", parts=["__lemur_probe_abc12345"])

    # Arg 1: Scalar_String with expr_key
    arg1 = FakeNode("arg1", "Arg")
    str_node = FakeNode("str1", "Scalar_String", value=expr_key)

    # Arg 2: original expression
    arg2 = FakeNode("arg2", "Arg")
    original = FakeNode("orig1", "Expr_Variable", name="total")

    ast._nodes = {n.id: n for n in [echo, func_call, name, arg1, str_node, arg2, original]}

    build_parent_child(ast, echo, func_call, field="exprs", index=0)
    build_parent_child(ast, func_call, name, field="name")
    build_parent_child(ast, func_call, arg1, field="args", index=0)
    build_parent_child(ast, func_call, arg2, field="args", index=1)
    build_parent_child(ast, arg1, str_node, field="value")
    build_parent_child(ast, arg2, original, field="value")

    return ast


@patch("lemur._operations._deinstrumenter.Modifier")
def test_unwrap_probe_ast_finds_and_replaces(mock_modifier_cls: MagicMock):
    ast = _build_probe_call_ast("total")
    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(Path("/test.php"), "total", ast)
    assert result is True


@patch("lemur._operations._deinstrumenter.Modifier")
def test_unwrap_probe_ast_not_found_returns_false(mock_modifier_cls: MagicMock):
    ast = _build_probe_call_ast("total")
    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(Path("/test.php"), "nonexistent", ast)
    assert result is False


def test_is_probe_call_matches_prefix():
    ast = FakeAST()
    func_call = FakeNode("call1", "Expr_FuncCall")
    name = FakeNode("name1", "Name", parts=["__lemur_probe_12345678"])
    ast._nodes = {n.id: n for n in [func_call, name]}
    build_parent_child(ast, func_call, name, field="name")

    deinstrumenter = ASTDeinstrumenter()
    assert deinstrumenter._is_probe_call(ast, func_call) is True


def test_is_probe_call_rejects_non_probe():
    ast = FakeAST()
    func_call = FakeNode("call1", "Expr_FuncCall")
    name = FakeNode("name1", "Name", parts=["some_function"])
    ast._nodes = {n.id: n for n in [func_call, name]}
    build_parent_child(ast, func_call, name, field="name")

    deinstrumenter = ASTDeinstrumenter()
    assert deinstrumenter._is_probe_call(ast, func_call) is False


def test_get_arg_by_index_returns_correct_arg():
    ast = FakeAST()
    func_call = FakeNode("call1", "Expr_FuncCall")
    arg0 = FakeNode("arg0", "Arg")
    arg1 = FakeNode("arg1", "Arg")
    ast._nodes = {n.id: n for n in [func_call, arg0, arg1]}
    build_parent_child(ast, func_call, arg0, field="args", index=0)
    build_parent_child(ast, func_call, arg1, field="args", index=1)

    deinstrumenter = ASTDeinstrumenter()
    assert deinstrumenter._get_arg_by_index(ast, func_call, 0) is arg0
    assert deinstrumenter._get_arg_by_index(ast, func_call, 1) is arg1
    assert deinstrumenter._get_arg_by_index(ast, func_call, 2) is None


@patch("lemur._operations._deinstrumenter.Modifier")
def test_replace_raises_on_orphan_call(mock_modifier_cls: MagicMock):
    ast = FakeAST()
    func_call = FakeNode("call1", "Expr_FuncCall")
    original = FakeNode("orig1", "Expr_Variable")
    ast._nodes = {n.id: n for n in [func_call, original]}

    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    deinstrumenter = ASTDeinstrumenter()
    with pytest.raises(DeinstrumentationError, match="Orphaned probe call"):
        deinstrumenter._replace_call_with_expression(
            ast, "call1", "orig1", Path("/test.php"),
        )


@patch("lemur._operations._deinstrumenter.Modifier")
def test_unwrap_tracks_exclude_node_ids(mock_modifier_cls: MagicMock):
    ast = _build_probe_call_ast("total")
    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    exclude: set[str] = set()
    deinstrumenter = ASTDeinstrumenter()
    deinstrumenter.unwrap_probe_ast(Path("/test.php"), "total", ast, exclude)
    assert "call1" in exclude
