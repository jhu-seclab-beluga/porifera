"""Tests for lemur._strategies."""

from conftest import FakeAST, FakeNode, build_parent_child
from lemur._strategies._base import ProbeStrategy, _is_safe_to_wrap
from lemur._strategies._elevating import ElevatingProbeStrategy
from lemur._strategies._standard import StandardProbeStrategy


def _build_assignment_ast() -> tuple[FakeAST, FakeNode, FakeNode]:
    """Build: Expr_Assign -> var: Expr_Variable, expr: Scalar_Int."""
    ast = FakeAST()
    assign = FakeNode("assign1", "Expr_Assign")
    var = FakeNode("var1", "Expr_Variable", name="x")
    rhs = FakeNode("rhs1", "Scalar_Int", value=42)
    ast._nodes = {n.id: n for n in [assign, var, rhs]}
    build_parent_child(ast, assign, var, field="var")
    build_parent_child(ast, assign, rhs, field="expr")
    return ast, var, rhs


def _build_for_loop_ast() -> tuple[FakeAST, FakeNode, FakeNode, FakeNode]:
    """Build: Stmt_For -> init: [Expr_Assign -> var: Expr_Variable]."""
    ast = FakeAST()
    for_stmt = FakeNode("for1", "Stmt_For")
    assign = FakeNode("assign1", "Expr_Assign")
    var = FakeNode("var1", "Expr_Variable", name="i")
    ast._nodes = {n.id: n for n in [for_stmt, assign, var]}
    build_parent_child(ast, for_stmt, assign, field="init", index=0)
    build_parent_child(ast, assign, var, field="var")
    return ast, for_stmt, assign, var


# --- _is_safe_to_wrap ---

def test_is_safe_to_wrap_rvalue_safe():
    ast, _var, rhs = _build_assignment_ast()
    assert _is_safe_to_wrap(ast, rhs) is True


def test_is_safe_to_wrap_lvalue_unsafe():
    ast, var, _rhs = _build_assignment_ast()
    assert _is_safe_to_wrap(ast, var) is False


def test_is_safe_to_wrap_reference_context_unsafe():
    ast = FakeAST()
    assign_ref = FakeNode("ref1", "Expr_AssignRef")
    rhs = FakeNode("rhs1", "Expr_Variable", name="y")
    ast._nodes = {n.id: n for n in [assign_ref, rhs]}
    build_parent_child(ast, assign_ref, rhs, field="expr")
    assert _is_safe_to_wrap(ast, rhs) is False


def test_is_safe_to_wrap_no_parent():
    ast = FakeAST()
    orphan = FakeNode("orphan", "Expr_Variable")
    ast._nodes = {"orphan": orphan}
    assert _is_safe_to_wrap(ast, orphan) is False


def test_is_safe_to_wrap_for_init_safe():
    ast, _for_stmt, assign, _var = _build_for_loop_ast()
    assert _is_safe_to_wrap(ast, assign) is True


def test_is_safe_to_wrap_for_loop_update_safe():
    ast = FakeAST()
    for_stmt = FakeNode("for1", "Stmt_For")
    post_inc = FakeNode("inc1", "Expr_PostInc")
    ast._nodes = {n.id: n for n in [for_stmt, post_inc]}
    build_parent_child(ast, for_stmt, post_inc, field="loop", index=0)
    assert _is_safe_to_wrap(ast, post_inc) is True


# --- StandardProbeStrategy ---

def test_standard_safe_returns_node():
    strategy = StandardProbeStrategy()
    ast, _var, rhs = _build_assignment_ast()
    result = strategy.select_wrap_target(ast, rhs, set())
    assert result is rhs


def test_standard_unsafe_returns_none():
    strategy = StandardProbeStrategy()
    ast, var, _rhs = _build_assignment_ast()
    result = strategy.select_wrap_target(ast, var, set())
    assert result is None


def test_standard_already_wrapped_returns_none():
    strategy = StandardProbeStrategy()
    ast, _var, rhs = _build_assignment_ast()
    result = strategy.select_wrap_target(ast, rhs, {rhs.id})
    assert result is None


# --- ElevatingProbeStrategy ---

def test_elevating_safe_returns_node_directly():
    strategy = ElevatingProbeStrategy()
    ast, _var, rhs = _build_assignment_ast()
    result = strategy.select_wrap_target(ast, rhs, set())
    assert result is rhs


def test_elevating_unsafe_elevates_to_ancestor():
    strategy = ElevatingProbeStrategy()
    ast, _for_stmt, assign, var = _build_for_loop_ast()
    result = strategy.select_wrap_target(ast, var, set())
    assert result is assign


def test_elevating_statement_boundary_returns_none():
    strategy = ElevatingProbeStrategy()
    ast = FakeAST()
    foreach = FakeNode("fe1", "Stmt_Foreach")
    key_var = FakeNode("kv1", "Expr_Variable", name="k")
    ast._nodes = {n.id: n for n in [foreach, key_var]}
    build_parent_child(ast, foreach, key_var, field="keyVar")
    result = strategy.select_wrap_target(ast, key_var, set())
    assert result is None


def test_elevating_wrapped_ancestor_returns_none():
    strategy = ElevatingProbeStrategy()
    ast, _for_stmt, assign, var = _build_for_loop_ast()
    result = strategy.select_wrap_target(ast, var, {assign.id})
    assert result is None


def test_elevating_for_loop_update_elevation():
    strategy = ElevatingProbeStrategy()
    ast = FakeAST()
    for_stmt = FakeNode("for1", "Stmt_For")
    post_inc = FakeNode("inc1", "Expr_PostInc")
    var = FakeNode("var1", "Expr_Variable", name="i")
    ast._nodes = {n.id: n for n in [for_stmt, post_inc, var]}
    build_parent_child(ast, for_stmt, post_inc, field="loop", index=0)
    build_parent_child(ast, post_inc, var, field="var")
    result = strategy.select_wrap_target(ast, var, set())
    assert result is post_inc


def test_elevating_already_wrapped_returns_none():
    strategy = ElevatingProbeStrategy()
    ast, _var, rhs = _build_assignment_ast()
    result = strategy.select_wrap_target(ast, rhs, {rhs.id})
    assert result is None
