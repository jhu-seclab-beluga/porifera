"""Tests for porifera._operations._instrumenter using real PHP code."""

from pathlib import Path

from php_parser_py import PrettyPrinter

from conftest import find_child, find_node, find_nodes, parse_php
from porifera._operations._instrumenter import _PROBE_FUNC_PREFIX, ASTInstrumenter
from porifera._strategies._standard import StandardProbeStrategy


def test_instrument_wraps_echo_string(tmp_path: Path):
    """Wrapping echo 'hello' produces __porifera_probe_xxx('key', 'hello')."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_test1234")
    result = instrumenter.instrument_node(target.id, "greeting")
    assert result is True

    pp = PrettyPrinter()
    output = pp.print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_test1234" in output
    assert "greeting" in output
    assert "hello" in output


def test_instrument_wraps_numeric_literal(tmp_path: Path):
    """Wrapping rvalue of $x = 42."""
    ast = parse_php(tmp_path, code='<?php\n$x = 42;\n')
    rhs = find_node(ast, "Scalar_LNumber")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_abc")
    result = instrumenter.instrument_node(rhs.id, "x_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_abc('x_val', 42)" in output


def test_instrument_skips_lvalue(tmp_path: Path):
    """Lvalue of assignment is not instrumented."""
    ast = parse_php(tmp_path, code='<?php\n$x = 42;\n')
    assign = find_node(ast, "Expr_Assign")
    lhs = find_child(ast, assign, "var")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_test")
    result = instrumenter.instrument_node(lhs.id, "x_var")
    assert result is False


def test_instrument_prevents_double_wrap(tmp_path: Path):
    """Same target cannot be wrapped twice."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_test")
    assert instrumenter.instrument_node(target.id, "key1") is True
    assert instrumenter.instrument_node(target.id, "key2") is False


def test_instrument_multiple_targets(tmp_path: Path):
    """Instrument multiple independent targets in the same file."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\necho "world";\n')
    strings = find_nodes(ast, "Scalar_String")
    assert len(strings) >= 2

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_multi")
    assert instrumenter.instrument_node(strings[0].id, "first") is True
    assert instrumenter.instrument_node(strings[1].id, "second") is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "'first'" in output
    assert "'second'" in output


def test_instrument_function_call_argument(tmp_path: Path):
    """Instrument a function call argument."""
    ast = parse_php(tmp_path, code='<?php\nfoo($a);\n')
    var = find_node(ast, "Expr_Variable")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_arg")
    result = instrumenter.instrument_node(var.id, "a_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_arg('a_val'" in output


def test_instrument_binary_op_rhs(tmp_path: Path):
    """Instrument the RHS of a binary operation $a + 1."""
    ast = parse_php(tmp_path, code='<?php\n$result = $a + 1;\n')
    rhs = find_node(ast, "Scalar_LNumber")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_binop")
    result = instrumenter.instrument_node(rhs.id, "rhs_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_binop('rhs_val', 1)" in output


def test_instrument_ternary_branch(tmp_path: Path):
    """Instrument a ternary if-branch value."""
    ast = parse_php(tmp_path, code='<?php\n$r = $a ? "yes" : "no";\n')
    strings = find_nodes(ast, "Scalar_String")
    yes_node = next(s for s in strings if s.get_property("value") == "yes")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_tern")
    result = instrumenter.instrument_node(yes_node.id, "yes_branch")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_tern('yes_branch'" in output


def test_probe_func_prefix_value():
    """Verify probe function prefix constant."""
    assert _PROBE_FUNC_PREFIX == "__porifera_probe_"


# --- Wrapping OOP constructs ---

def test_instrument_wraps_method_call_result(tmp_path: Path):
    """Wrapping $obj->getStatus() in assignment rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$result = $obj->getStatus();\n')
    method_call = find_node(ast, "Expr_MethodCall")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_method")
    result = instrumenter.instrument_node(method_call.id, "status_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_method('status_val'" in output


def test_instrument_wraps_static_method_call(tmp_path: Path):
    """Wrapping Foo::create() in assignment rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$obj = Foo::create();\n')
    static_call = find_node(ast, "Expr_StaticCall")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_static")
    result = instrumenter.instrument_node(static_call.id, "create_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_static('create_val'" in output


def test_instrument_wraps_property_fetch(tmp_path: Path):
    """Wrapping $obj->name in echo."""
    ast = parse_php(tmp_path, code='<?php\necho $obj->name;\n')
    prop = find_node(ast, "Expr_PropertyFetch")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_prop")
    result = instrumenter.instrument_node(prop.id, "name_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_prop('name_val'" in output


def test_instrument_wraps_new_instance(tmp_path: Path):
    """Wrapping new Foo() in assignment rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$obj = new Foo();\n')
    new_expr = find_node(ast, "Expr_New")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_new")
    result = instrumenter.instrument_node(new_expr.id, "new_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_new('new_val'" in output


def test_instrument_wraps_class_constant(tmp_path: Path):
    """Wrapping Foo::BAR in assignment rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$val = Foo::BAR;\n')
    const_fetch = find_node(ast, "Expr_ClassConstFetch")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_const")
    result = instrumenter.instrument_node(const_fetch.id, "const_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_const('const_val'" in output


# --- Wrapping complex expressions ---

def test_instrument_wraps_null_coalesce(tmp_path: Path):
    """Wrapping $a ?? $b as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$result = $a ?? $b;\n')
    coalesce = find_node(ast, "Expr_BinaryOp_Coalesce")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_coal")
    result = instrumenter.instrument_node(coalesce.id, "coalesce_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_coal('coalesce_val'" in output


def test_instrument_wraps_cast_expression(tmp_path: Path):
    """Wrapping (int)$x as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$val = (int)$x;\n')
    cast = find_node(ast, "Expr_Cast_Int")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_cast")
    result = instrumenter.instrument_node(cast.id, "cast_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_cast('cast_val'" in output


def test_instrument_wraps_boolean_not(tmp_path: Path):
    """Wrapping !$x as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$val = !$x;\n')
    not_expr = find_node(ast, "Expr_BooleanNot")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_not")
    result = instrumenter.instrument_node(not_expr.id, "not_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_not('not_val'" in output


def test_instrument_wraps_instanceof(tmp_path: Path):
    """Wrapping $x instanceof Foo as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$check = $x instanceof Foo;\n')
    instanceof = find_node(ast, "Expr_Instanceof")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_inst")
    result = instrumenter.instrument_node(instanceof.id, "inst_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_inst('inst_val'" in output


def test_instrument_wraps_string_concat(tmp_path: Path):
    """Wrapping $a . $b as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$result = $a . $b;\n')
    concat = find_node(ast, "Expr_BinaryOp_Concat")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_concat")
    result = instrumenter.instrument_node(concat.id, "concat_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_concat('concat_val'" in output


def test_instrument_wraps_array_literal(tmp_path: Path):
    """Wrapping [1, 2, 3] as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$arr = [1, 2, 3];\n')
    array_expr = find_node(ast, "Expr_Array")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_arr")
    result = instrumenter.instrument_node(array_expr.id, "arr_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_arr('arr_val'" in output


def test_instrument_wraps_closure(tmp_path: Path):
    """Wrapping closure as function argument."""
    ast = parse_php(tmp_path, code='<?php\narray_map(function($x) { return $x * 2; }, $arr);\n')
    closure = find_node(ast, "Expr_Closure")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_cls")
    result = instrumenter.instrument_node(closure.id, "closure_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_cls('closure_val'" in output


def test_instrument_wraps_arrow_function(tmp_path: Path):
    """Wrapping fn($x) => $x + 1 as rvalue."""
    ast = parse_php(tmp_path, code='<?php\n$fn = fn($x) => $x + 1;\n')
    arrow = find_node(ast, "Expr_ArrowFunction")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_arrow")
    result = instrumenter.instrument_node(arrow.id, "arrow_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_arrow('arrow_val'" in output


# --- Wrapping in complex PHP structures ---

def test_instrument_wraps_inside_class_method(tmp_path: Path):
    """Wrapping expression inside a class method body."""
    code = '<?php\nclass Calculator {\n    public function add($a, $b) {\n        return $a + $b;\n    }\n}\n'
    ast = parse_php(tmp_path, code=code)
    plus = find_node(ast, "Expr_BinaryOp_Plus")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_cls_m")
    result = instrumenter.instrument_node(plus.id, "add_result")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_cls_m('add_result'" in output


def test_instrument_wraps_inside_if_condition(tmp_path: Path):
    """Wrapping function call inside if condition."""
    code = '<?php\nif (is_valid($input)) {\n    echo "ok";\n}\n'
    ast = parse_php(tmp_path, code=code)
    func_call = find_node(ast, "Expr_FuncCall")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_if")
    result = instrumenter.instrument_node(func_call.id, "cond_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_if('cond_val'" in output


def test_instrument_wraps_inside_while_condition(tmp_path: Path):
    """Wrapping expression inside while condition."""
    code = '<?php\nwhile ($count > 0) {\n    $count--;\n}\n'
    ast = parse_php(tmp_path, code=code)
    gt = find_node(ast, "Expr_BinaryOp_Greater")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_while")
    result = instrumenter.instrument_node(gt.id, "cond_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_while('cond_val'" in output


def test_instrument_multiple_targets_complex_code(tmp_path: Path):
    """Instrument multiple targets in code with classes and control flow."""
    code = '<?php\nclass Svc {\n    public function run($x) {\n        $a = $x + 1;\n        return $a * 2;\n    }\n}\n'
    ast = parse_php(tmp_path, code=code)
    plus = find_node(ast, "Expr_BinaryOp_Plus")
    mul = find_node(ast, "Expr_BinaryOp_Mul")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__porifera_probe_multi")
    assert instrumenter.instrument_node(plus.id, "add_op") is True
    assert instrumenter.instrument_node(mul.id, "mul_op") is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "'add_op'" in output
    assert "'mul_op'" in output


# --- Elevation-based wrapping ---

def test_instrument_elevating_wraps_post_increment(tmp_path: Path):
    """ElevatingProbeStrategy wraps $i++ by elevating to PostInc expression."""
    from porifera._strategies._elevating import ElevatingProbeStrategy

    ast = parse_php(tmp_path, code='<?php\nfor ($i = 0; $i < 5; $i++) {}\n')
    post_inc = find_node(ast, "Expr_PostInc")
    var = find_child(ast, post_inc, "var")
    assert var is not None

    instrumenter = ASTInstrumenter(ast, ElevatingProbeStrategy(), "__porifera_probe_elev")
    result = instrumenter.instrument_node(var.id, "inc_val")
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__porifera_probe_elev('inc_val'" in output


def test_instrument_elevating_skips_foreach_key(tmp_path: Path):
    """ElevatingProbeStrategy skips foreach key var (no Expr ancestor)."""
    from porifera._strategies._elevating import ElevatingProbeStrategy

    ast = parse_php(tmp_path, code='<?php\nforeach ($items as $k => $v) { echo $v; }\n')
    foreach = find_node(ast, "Stmt_Foreach")
    key_var = find_child(ast, foreach, "keyVar")
    assert key_var is not None

    instrumenter = ASTInstrumenter(ast, ElevatingProbeStrategy(), "__porifera_probe_elev")
    result = instrumenter.instrument_node(key_var.id, "key_val")
    assert result is False
