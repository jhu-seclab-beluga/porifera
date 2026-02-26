"""Tests for lemur._instrumenter."""

from unittest.mock import MagicMock, patch

import pytest

from conftest import FakeAST, FakeEdge, FakeModifier, FakeNode, build_parent_child
from lemur._exceptions import InstrumentationError
from lemur._operations._instrumenter import _PROBE_FUNC_PREFIX, ASTInstrumenter
from lemur._strategies._standard import StandardProbeStrategy


def _build_simple_ast() -> tuple[FakeAST, FakeNode]:
    """Build: Stmt_Echo -> exprs[0]: Scalar_String."""
    ast = FakeAST()
    echo = FakeNode("echo1", "Stmt_Echo")
    string = FakeNode("str1", "Scalar_String", value="hello", startLine=5, endLine=5)
    ast._nodes = {n.id: n for n in [echo, string]}
    build_parent_child(ast, echo, string, field="exprs", index=0)
    return ast, string


@patch("lemur._operations._instrumenter.Modifier")
def test_instrument_node_wraps_target(mock_modifier_cls: MagicMock):
    ast, target = _build_simple_ast()
    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    strategy = StandardProbeStrategy()
    instrumenter = ASTInstrumenter(ast, strategy, "__lemur_probe_test1234")
    result = instrumenter.instrument_node("str1", "greeting")
    assert result is True


@patch("lemur._operations._instrumenter.Modifier")
def test_instrument_node_skips_no_safe_target(mock_modifier_cls: MagicMock):
    ast = FakeAST()
    assign = FakeNode("assign1", "Expr_Assign")
    var = FakeNode("var1", "Expr_Variable", name="x")
    ast._nodes = {n.id: n for n in [assign, var]}
    build_parent_child(ast, assign, var, field="var")

    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    strategy = StandardProbeStrategy()
    instrumenter = ASTInstrumenter(ast, strategy, "__lemur_probe_test1234")
    result = instrumenter.instrument_node("var1", "x_val")
    assert result is False


@patch("lemur._operations._instrumenter.Modifier")
def test_instrument_node_prevents_double_wrap(mock_modifier_cls: MagicMock):
    ast, target = _build_simple_ast()
    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    strategy = StandardProbeStrategy()
    instrumenter = ASTInstrumenter(ast, strategy, "__lemur_probe_test1234")
    assert instrumenter.instrument_node("str1", "greeting") is True
    # Second call on same target should skip (already wrapped)
    assert instrumenter.instrument_node("str1", "greeting2") is False


@patch("lemur._operations._instrumenter.Modifier")
def test_instrument_node_creates_correct_structure(mock_modifier_cls: MagicMock):
    ast, target = _build_simple_ast()
    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_abc")
    instrumenter.instrument_node("str1", "greeting")

    # Verify nodes were created: Expr_FuncCall, Name, Scalar_String (key), 2 Args
    created_types = {n.node_type for n in ast._nodes.values() if n.id.startswith("probe_")}
    assert "Expr_FuncCall" in created_types
    assert "Name" in created_types
    assert "Arg" in created_types

    # Verify the Name node has the probe function name
    name_nodes = [n for n in ast._nodes.values() if n.node_type == "Name" and n.id.startswith("probe_")]
    assert len(name_nodes) == 1
    assert name_nodes[0].get_property("parts") == ["__lemur_probe_abc"]


@patch("lemur._operations._instrumenter.Modifier")
def test_instrument_node_raises_on_orphan_node(mock_modifier_cls: MagicMock):
    ast = FakeAST()
    orphan = FakeNode("orphan1", "Scalar_String", value="test")
    ast._nodes = {"orphan1": orphan}

    mock_modifier = FakeModifier(ast)
    mock_modifier_cls.return_value = mock_modifier

    # Use a strategy that always returns the node
    strategy = MagicMock()
    strategy.select_wrap_target.return_value = orphan

    instrumenter = ASTInstrumenter(ast, strategy, "__lemur_probe_test")
    with pytest.raises(InstrumentationError, match="no parent edge"):
        instrumenter.instrument_node("orphan1", "test")


def test_probe_func_prefix_value():
    assert _PROBE_FUNC_PREFIX == "__lemur_probe_"
