"""Tests for lemur._strategies using real PHP code."""

from pathlib import Path

from conftest import find_child, find_node, find_nodes, parse_php
from lemur._strategies._base import _is_safe_to_wrap
from lemur._strategies._elevating import ElevatingProbeStrategy
from lemur._strategies._standard import StandardProbeStrategy


# --- _is_safe_to_wrap: rvalue contexts (safe) ---

def test_safe_to_wrap_assignment_rvalue(tmp_path: Path):
    """Rvalue of $x = 42 is safe to wrap."""
    ast = parse_php(tmp_path, code='<?php\n$x = 42;\n')
    rhs = find_node(ast, "Scalar_LNumber")
    assert _is_safe_to_wrap(ast, rhs) is True


def test_safe_to_wrap_echo_expression(tmp_path: Path):
    """Expression in echo $x is safe to wrap."""
    ast = parse_php(tmp_path, code='<?php\necho $x;\n')
    var = find_node(ast, "Expr_Variable")
    assert _is_safe_to_wrap(ast, var) is True


def test_safe_to_wrap_return_expression(tmp_path: Path):
    """Expression in return $x + 1 is safe."""
    ast = parse_php(tmp_path, code='<?php\nfunction f() { return $x + 1; }\n')
    plus = find_node(ast, "Expr_BinaryOp_Plus")
    assert _is_safe_to_wrap(ast, plus) is True


def test_safe_to_wrap_function_argument(tmp_path: Path):
    """Function argument value is safe."""
    ast = parse_php(tmp_path, code='<?php\nfoo($a);\n')
    var = find_node(ast, "Expr_Variable")
    assert _is_safe_to_wrap(ast, var) is True


def test_safe_to_wrap_concat_rvalue(tmp_path: Path):
    """Rvalue of $x .= 'str' is safe."""
    ast = parse_php(tmp_path, code='<?php\n$x .= "str";\n')
    rhs = find_node(ast, "Scalar_String")
    assert _is_safe_to_wrap(ast, rhs) is True


def test_safe_to_wrap_ternary_condition(tmp_path: Path):
    """Condition of ternary $a ? $b : $c is safe."""
    ast = parse_php(tmp_path, code='<?php\n$result = $a ? $b : $c;\n')
    ternary = find_node(ast, "Expr_Ternary")
    cond = find_child(ast, ternary, "cond")
    assert cond is not None
    assert _is_safe_to_wrap(ast, cond) is True


def test_safe_to_wrap_array_dim_value(tmp_path: Path):
    """Array dimension index $arr[$idx] — the dim is safe."""
    ast = parse_php(tmp_path, code='<?php\necho $arr[$idx];\n')
    fetch = find_node(ast, "Expr_ArrayDimFetch")
    dim = find_child(ast, fetch, "dim")
    assert dim is not None
    assert _is_safe_to_wrap(ast, dim) is True


# --- _is_safe_to_wrap: lvalue contexts (unsafe) ---

def test_unsafe_assignment_lvalue(tmp_path: Path):
    """Lvalue of $x = 42 is NOT safe to wrap."""
    ast = parse_php(tmp_path, code='<?php\n$x = 42;\n')
    assign = find_node(ast, "Expr_Assign")
    lhs = find_child(ast, assign, "var")
    assert lhs is not None
    assert _is_safe_to_wrap(ast, lhs) is False


def test_unsafe_compound_assignment_lvalue(tmp_path: Path):
    """Lvalue of $x += 1 is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n$x += 1;\n')
    assign_op = find_node(ast, "Expr_AssignOp_Plus")
    lhs = find_child(ast, assign_op, "var")
    assert lhs is not None
    assert _is_safe_to_wrap(ast, lhs) is False


def test_unsafe_concat_assignment_lvalue(tmp_path: Path):
    """Lvalue of $x .= 'str' is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n$x .= "str";\n')
    assign_op = find_node(ast, "Expr_AssignOp_Concat")
    lhs = find_child(ast, assign_op, "var")
    assert lhs is not None
    assert _is_safe_to_wrap(ast, lhs) is False


def test_unsafe_post_increment_var(tmp_path: Path):
    """Variable in $i++ is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n$i++;\n')
    post_inc = find_node(ast, "Expr_PostInc")
    var = find_child(ast, post_inc, "var")
    assert var is not None
    assert _is_safe_to_wrap(ast, var) is False


def test_unsafe_pre_increment_var(tmp_path: Path):
    """Variable in ++$j is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n++$j;\n')
    pre_inc = find_node(ast, "Expr_PreInc")
    var = find_child(ast, pre_inc, "var")
    assert var is not None
    assert _is_safe_to_wrap(ast, var) is False


def test_unsafe_foreach_key_var(tmp_path: Path):
    """Key variable in foreach is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\nforeach ($arr as $k => $v) {}\n')
    foreach = find_node(ast, "Stmt_Foreach")
    key_var = find_child(ast, foreach, "keyVar")
    assert key_var is not None
    assert _is_safe_to_wrap(ast, key_var) is False


def test_unsafe_foreach_value_var(tmp_path: Path):
    """Value variable in foreach is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\nforeach ($arr as $k => $v) {}\n')
    foreach = find_node(ast, "Stmt_Foreach")
    val_var = find_child(ast, foreach, "valueVar")
    assert val_var is not None
    assert _is_safe_to_wrap(ast, val_var) is False


# --- _is_safe_to_wrap: reference contexts (unsafe) ---

def test_unsafe_reference_assignment_expr(tmp_path: Path):
    """Expr of $y = &$x is NOT safe (reference context)."""
    ast = parse_php(tmp_path, code='<?php\n$y = &$x;\n')
    ref = find_node(ast, "Expr_AssignRef")
    expr = find_child(ast, ref, "expr")
    assert expr is not None
    assert _is_safe_to_wrap(ast, expr) is False


def test_unsafe_reference_assignment_var(tmp_path: Path):
    """Var of $y = &$x is NOT safe (lvalue context)."""
    ast = parse_php(tmp_path, code='<?php\n$y = &$x;\n')
    ref = find_node(ast, "Expr_AssignRef")
    var = find_child(ast, ref, "var")
    assert var is not None
    assert _is_safe_to_wrap(ast, var) is False


# --- _is_safe_to_wrap: for loop contexts ---

def test_safe_for_init_assignment(tmp_path: Path):
    """Expr_Assign in for-init is safe (field=init, parent=Stmt_For)."""
    ast = parse_php(tmp_path, code='<?php\nfor ($i = 0; $i < 10; $i++) {}\n')
    for_stmt = find_node(ast, "Stmt_For")
    init_assigns = [
        c for c in ast.succ(for_stmt)
        if ast.edge(for_stmt.id, c.id, "PARENT_OF").get("field") == "init"
    ]
    assert len(init_assigns) == 1
    assert _is_safe_to_wrap(ast, init_assigns[0]) is True


def test_safe_for_loop_update(tmp_path: Path):
    """PostInc in for-loop update is safe (field=loop, parent=Stmt_For)."""
    ast = parse_php(tmp_path, code='<?php\nfor ($i = 0; $i < 10; $i++) {}\n')
    for_stmt = find_node(ast, "Stmt_For")
    loop_exprs = [
        c for c in ast.succ(for_stmt)
        if ast.edge(for_stmt.id, c.id, "PARENT_OF").get("field") == "loop"
    ]
    assert len(loop_exprs) == 1
    assert _is_safe_to_wrap(ast, loop_exprs[0]) is True


# --- StandardProbeStrategy ---

def test_standard_selects_safe_rvalue(tmp_path: Path):
    """StandardProbeStrategy returns rvalue node directly."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")
    strategy = StandardProbeStrategy()
    result = strategy.select_wrap_target(ast, target, set())
    assert result is target


def test_standard_returns_none_for_lvalue(tmp_path: Path):
    """StandardProbeStrategy returns None for lvalue."""
    ast = parse_php(tmp_path, code='<?php\n$x = 42;\n')
    assign = find_node(ast, "Expr_Assign")
    lhs = find_child(ast, assign, "var")
    strategy = StandardProbeStrategy()
    result = strategy.select_wrap_target(ast, lhs, set())
    assert result is None


def test_standard_returns_none_for_already_wrapped(tmp_path: Path):
    """StandardProbeStrategy returns None for already-wrapped node."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")
    strategy = StandardProbeStrategy()
    result = strategy.select_wrap_target(ast, target, {target.id})
    assert result is None


# --- ElevatingProbeStrategy ---

def test_elevating_returns_safe_node_directly(tmp_path: Path):
    """ElevatingProbeStrategy returns safe node directly without elevation."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, target, set())
    assert result is target


def test_elevating_unsafe_elevates_to_ancestor(tmp_path: Path):
    """ElevatingProbeStrategy elevates $i++ var to the PostInc."""
    ast = parse_php(tmp_path, code='<?php\nfor ($i = 0; $i < 10; $i++) {}\n')
    post_inc = find_node(ast, "Expr_PostInc")
    var = find_child(ast, post_inc, "var")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, var, set())
    assert result is not None
    assert result.id == post_inc.id


def test_elevating_foreach_key_returns_none(tmp_path: Path):
    """ElevatingProbeStrategy returns None for foreach keyVar (no Expr ancestor)."""
    ast = parse_php(tmp_path, code='<?php\nforeach ($arr as $k => $v) {}\n')
    foreach = find_node(ast, "Stmt_Foreach")
    key_var = find_child(ast, foreach, "keyVar")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, key_var, set())
    assert result is None


def test_elevating_already_wrapped_returns_none(tmp_path: Path):
    """ElevatingProbeStrategy returns None for already-wrapped node."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, target, {target.id})
    assert result is None


def test_elevating_wrapped_ancestor_returns_none(tmp_path: Path):
    """ElevatingProbeStrategy returns None if ancestor is already wrapped."""
    ast = parse_php(tmp_path, code='<?php\nfor ($i = 0; $i < 10; $i++) {}\n')
    post_inc = find_node(ast, "Expr_PostInc")
    var = find_child(ast, post_inc, "var")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, var, {post_inc.id})
    assert result is None


def test_elevating_nested_assignment_var(tmp_path: Path):
    """ElevatingProbeStrategy elevates nested assignment lvalue to the Expr_Assign."""
    ast = parse_php(tmp_path, code='<?php\nfor ($i = 0; $i < 10; $i++) {}\n')
    for_stmt = find_node(ast, "Stmt_For")
    assigns = [
        c for c in ast.succ(for_stmt)
        if ast.edge(for_stmt.id, c.id, "PARENT_OF").get("field") == "init"
    ]
    assign = assigns[0]
    var = find_child(ast, assign, "var")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, var, set())
    assert result is not None
    assert result.id == assign.id


# --- _is_safe_to_wrap: OOP constructs ---

def test_safe_to_wrap_method_call_result(tmp_path: Path):
    """Method call result as rvalue in assignment is safe."""
    ast = parse_php(tmp_path, code='<?php\n$result = $obj->getStatus();\n')
    method_call = find_node(ast, "Expr_MethodCall")
    assert _is_safe_to_wrap(ast, method_call) is True


def test_safe_to_wrap_static_method_call_result(tmp_path: Path):
    """Static method call result as rvalue in assignment is safe."""
    ast = parse_php(tmp_path, code='<?php\n$result = Foo::create();\n')
    static_call = find_node(ast, "Expr_StaticCall")
    assert _is_safe_to_wrap(ast, static_call) is True


def test_safe_to_wrap_property_fetch_in_echo(tmp_path: Path):
    """Property access $obj->name in echo is safe."""
    ast = parse_php(tmp_path, code='<?php\necho $obj->name;\n')
    prop_fetch = find_node(ast, "Expr_PropertyFetch")
    assert _is_safe_to_wrap(ast, prop_fetch) is True


def test_safe_to_wrap_class_constant_fetch(tmp_path: Path):
    """Class constant Foo::BAR as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$val = Foo::BAR;\n')
    const_fetch = find_node(ast, "Expr_ClassConstFetch")
    assert _is_safe_to_wrap(ast, const_fetch) is True


def test_safe_to_wrap_new_instance(tmp_path: Path):
    """new Foo() in assignment rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$obj = new Foo();\n')
    new_expr = find_node(ast, "Expr_New")
    assert _is_safe_to_wrap(ast, new_expr) is True


def test_safe_to_wrap_instanceof_check(tmp_path: Path):
    """$x instanceof Foo as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$check = $x instanceof Foo;\n')
    instanceof = find_node(ast, "Expr_Instanceof")
    assert _is_safe_to_wrap(ast, instanceof) is True


# --- _is_safe_to_wrap: null coalescing / casting / unary ---

def test_safe_to_wrap_null_coalesce_rvalue(tmp_path: Path):
    """Null coalescing $a ?? $b as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$result = $a ?? $b;\n')
    coalesce = find_node(ast, "Expr_BinaryOp_Coalesce")
    assert _is_safe_to_wrap(ast, coalesce) is True


def test_safe_to_wrap_cast_int(tmp_path: Path):
    """(int)$x as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$val = (int)$x;\n')
    cast = find_node(ast, "Expr_Cast_Int")
    assert _is_safe_to_wrap(ast, cast) is True


def test_safe_to_wrap_cast_string(tmp_path: Path):
    """(string)$x as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$val = (string)$x;\n')
    cast = find_node(ast, "Expr_Cast_String")
    assert _is_safe_to_wrap(ast, cast) is True


def test_safe_to_wrap_boolean_not(tmp_path: Path):
    """!$x as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$val = !$x;\n')
    not_expr = find_node(ast, "Expr_BooleanNot")
    assert _is_safe_to_wrap(ast, not_expr) is True


def test_safe_to_wrap_unary_minus(tmp_path: Path):
    """-$x as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$val = -$x;\n')
    neg = find_node(ast, "Expr_UnaryMinus")
    assert _is_safe_to_wrap(ast, neg) is True


# --- _is_safe_to_wrap: complex expressions ---

def test_safe_to_wrap_string_concat_rvalue(tmp_path: Path):
    """$a . $b as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$result = $a . $b;\n')
    concat = find_node(ast, "Expr_BinaryOp_Concat")
    assert _is_safe_to_wrap(ast, concat) is True


def test_safe_to_wrap_comparison_identical(tmp_path: Path):
    """$a === $b as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$check = $a === $b;\n')
    cmp = find_node(ast, "Expr_BinaryOp_Identical")
    assert _is_safe_to_wrap(ast, cmp) is True


def test_safe_to_wrap_logical_and(tmp_path: Path):
    """$a && $b as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$check = $a && $b;\n')
    logical = find_node(ast, "Expr_BinaryOp_BooleanAnd")
    assert _is_safe_to_wrap(ast, logical) is True


def test_safe_to_wrap_logical_or(tmp_path: Path):
    """$a || $b as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$check = $a || $b;\n')
    logical = find_node(ast, "Expr_BinaryOp_BooleanOr")
    assert _is_safe_to_wrap(ast, logical) is True


def test_safe_to_wrap_spaceship_operator(tmp_path: Path):
    """$a <=> $b as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$cmp = $a <=> $b;\n')
    spaceship = find_node(ast, "Expr_BinaryOp_Spaceship")
    assert _is_safe_to_wrap(ast, spaceship) is True


def test_safe_to_wrap_nested_function_call_arg(tmp_path: Path):
    """Inner call argument in foo(bar($x)) — $x is safe."""
    ast = parse_php(tmp_path, code='<?php\nfoo(bar($x));\n')
    vars_ = find_nodes(ast, "Expr_Variable")
    x_var = next(v for v in vars_ if v.get_property("name") == "x")
    assert _is_safe_to_wrap(ast, x_var) is True


def test_safe_to_wrap_chained_method_call(tmp_path: Path):
    """Chained method result $obj->a()->b() as echo arg is safe."""
    ast = parse_php(tmp_path, code='<?php\necho $obj->a()->b();\n')
    method_calls = find_nodes(ast, "Expr_MethodCall")
    # The outermost method call (->b()) is child of echo
    outer = method_calls[-1]
    assert _is_safe_to_wrap(ast, outer) is True


def test_safe_to_wrap_array_literal_rvalue(tmp_path: Path):
    """Array literal [1, 2, 3] as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$arr = [1, 2, 3];\n')
    array_expr = find_node(ast, "Expr_Array")
    assert _is_safe_to_wrap(ast, array_expr) is True


def test_safe_to_wrap_closure_as_argument(tmp_path: Path):
    """Closure passed as function argument is safe."""
    ast = parse_php(tmp_path, code='<?php\narray_map(function($x) { return $x * 2; }, $arr);\n')
    closure = find_node(ast, "Expr_Closure")
    assert _is_safe_to_wrap(ast, closure) is True


def test_safe_to_wrap_arrow_function_rvalue(tmp_path: Path):
    """Arrow function fn($x) => $x + 1 as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$fn = fn($x) => $x + 1;\n')
    arrow = find_node(ast, "Expr_ArrowFunction")
    assert _is_safe_to_wrap(ast, arrow) is True


def test_safe_to_wrap_ternary_if_branch(tmp_path: Path):
    """If-branch of ternary is safe."""
    ast = parse_php(tmp_path, code='<?php\n$r = $a ? $b + 1 : $c;\n')
    ternary = find_node(ast, "Expr_Ternary")
    if_branch = find_child(ast, ternary, "if")
    assert if_branch is not None
    assert _is_safe_to_wrap(ast, if_branch) is True


def test_safe_to_wrap_ternary_else_branch(tmp_path: Path):
    """Else-branch of ternary is safe."""
    ast = parse_php(tmp_path, code='<?php\n$r = $a ? $b : $c + 1;\n')
    ternary = find_node(ast, "Expr_Ternary")
    else_branch = find_child(ast, ternary, "else")
    assert else_branch is not None
    assert _is_safe_to_wrap(ast, else_branch) is True


# --- _is_safe_to_wrap: more unsafe contexts ---

def test_unsafe_pre_decrement_var(tmp_path: Path):
    """Variable in --$j is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n--$j;\n')
    pre_dec = find_node(ast, "Expr_PreDec")
    var = find_child(ast, pre_dec, "var")
    assert var is not None
    assert _is_safe_to_wrap(ast, var) is False


def test_unsafe_post_decrement_var(tmp_path: Path):
    """Variable in $j-- is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n$j--;\n')
    post_dec = find_node(ast, "Expr_PostDec")
    var = find_child(ast, post_dec, "var")
    assert var is not None
    assert _is_safe_to_wrap(ast, var) is False


def test_unsafe_unset_var(tmp_path: Path):
    """Variable in unset($x) is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\nunset($x);\n')
    unset_stmt = find_node(ast, "Stmt_Unset")
    children = list(ast.succ(unset_stmt))
    var = next(
        c for c in children
        if ast.edge(unset_stmt.id, c.id, "PARENT_OF").get("field") == "vars"
    )
    assert _is_safe_to_wrap(ast, var) is False


def test_unsafe_bitwise_and_assign_lvalue(tmp_path: Path):
    """Lvalue of $x &= 0xFF is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n$x &= 0xFF;\n')
    assign_op = find_node(ast, "Expr_AssignOp_BitwiseAnd")
    lhs = find_child(ast, assign_op, "var")
    assert lhs is not None
    assert _is_safe_to_wrap(ast, lhs) is False


def test_unsafe_shift_left_assign_lvalue(tmp_path: Path):
    """Lvalue of $x <<= 2 is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n$x <<= 2;\n')
    assign_op = find_node(ast, "Expr_AssignOp_ShiftLeft")
    lhs = find_child(ast, assign_op, "var")
    assert lhs is not None
    assert _is_safe_to_wrap(ast, lhs) is False


def test_unsafe_pow_assign_lvalue(tmp_path: Path):
    """Lvalue of $x **= 2 is NOT safe."""
    ast = parse_php(tmp_path, code='<?php\n$x **= 2;\n')
    assign_op = find_node(ast, "Expr_AssignOp_Pow")
    lhs = find_child(ast, assign_op, "var")
    assert lhs is not None
    assert _is_safe_to_wrap(ast, lhs) is False


def test_unsafe_coalesce_assign_lvalue(tmp_path: Path):
    """Lvalue of $x ??= 'default' is NOT safe."""
    ast = parse_php(tmp_path, code="<?php\n$x ??= 'default';\n")
    assign_op = find_node(ast, "Expr_AssignOp_Coalesce")
    lhs = find_child(ast, assign_op, "var")
    assert lhs is not None
    assert _is_safe_to_wrap(ast, lhs) is False


# --- _is_safe_to_wrap: complex multi-expression PHP ---

def test_safe_nested_ternary_inner_condition(tmp_path: Path):
    """Inner ternary condition in nested ternary is safe."""
    ast = parse_php(tmp_path, code='<?php\n$r = $a ? ($b ? "yes" : "maybe") : "no";\n')
    ternaries = find_nodes(ast, "Expr_Ternary")
    # Find the inner ternary whose condition is $b
    inner = None
    for t in ternaries:
        cond = find_child(ast, t, "cond")
        if cond is not None and cond.get_property("name") == "b":
            inner = t
            break
    assert inner is not None
    cond = find_child(ast, inner, "cond")
    assert cond is not None
    assert _is_safe_to_wrap(ast, cond) is True


def test_safe_method_call_on_new_instance(tmp_path: Path):
    """(new Foo())->bar() as rvalue is safe."""
    ast = parse_php(tmp_path, code='<?php\n$result = (new Foo())->bar();\n')
    method_call = find_node(ast, "Expr_MethodCall")
    assert _is_safe_to_wrap(ast, method_call) is True


def test_safe_array_dim_on_method_result(tmp_path: Path):
    """$obj->getData()[0] — the ArrayDimFetch is safe as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$val = $obj->getData()[0];\n')
    fetch = find_node(ast, "Expr_ArrayDimFetch")
    assert _is_safe_to_wrap(ast, fetch) is True


def test_safe_concatenation_with_method_call(tmp_path: Path):
    """'prefix_' . $obj->getName() — concat expr is safe as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$label = "prefix_" . $obj->getName();\n')
    concat = find_node(ast, "Expr_BinaryOp_Concat")
    assert _is_safe_to_wrap(ast, concat) is True


def test_safe_ternary_with_instanceof(tmp_path: Path):
    """$x instanceof Foo ? $x->bar() : null — condition is safe."""
    ast = parse_php(tmp_path, code='<?php\n$r = $x instanceof Foo ? $x->bar() : null;\n')
    ternary = find_node(ast, "Expr_Ternary")
    cond = find_child(ast, ternary, "cond")
    assert cond is not None
    assert _is_safe_to_wrap(ast, cond) is True


# --- ElevatingProbeStrategy: complex elevation scenarios ---

def test_elevating_property_assign_lvalue(tmp_path: Path):
    """Elevating $this->prop in $this->prop = $val elevates to Expr_Assign."""
    ast = parse_php(tmp_path, code='<?php\nclass A { function f() { $this->prop = $val; } }\n')
    assign = find_node(ast, "Expr_Assign")
    lhs = find_child(ast, assign, "var")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, lhs, set())
    assert result is not None
    assert result.id == assign.id


def test_elevating_pre_decrement_to_expr(tmp_path: Path):
    """Elevating --$j var to PreDec expression."""
    ast = parse_php(tmp_path, code='<?php\nfor ($i = 0; $i > -10; --$i) {}\n')
    pre_dec = find_node(ast, "Expr_PreDec")
    var = find_child(ast, pre_dec, "var")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, var, set())
    assert result is not None
    assert result.id == pre_dec.id


def test_elevating_compound_mul_assign_lvalue(tmp_path: Path):
    """Elevating $x in $x *= 2 to Expr_AssignOp_Mul."""
    ast = parse_php(tmp_path, code='<?php\n$total = 1;\n$total *= 5;\n')
    assign_op = find_node(ast, "Expr_AssignOp_Mul")
    lhs = find_child(ast, assign_op, "var")
    strategy = ElevatingProbeStrategy()
    result = strategy.select_wrap_target(ast, lhs, set())
    assert result is not None
    assert result.id == assign_op.id
