"""Tests for lemur._operations._deinstrumenter using real PHP code."""

from pathlib import Path

from php_parser_py import PrettyPrinter

from conftest import find_node, find_nodes, parse_php, write_php
from lemur._operations._deinstrumenter import ASTDeinstrumenter
from lemur._operations._instrumenter import ASTInstrumenter, _PROBE_FUNC_PREFIX
from lemur._strategies._standard import StandardProbeStrategy


# --- unwrap_probe_ast ---

def test_unwrap_restores_echo_string(tmp_path: Path):
    """Instrument echo 'hello', then unwrap — output should have no probe."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_test1234")
    instrumenter.instrument_node(target.id, "greeting")

    # Verify instrumented
    rel_path = ast.file_nodes()[0].get_property("relativePath")
    output = PrettyPrinter().print_file(ast, rel_path)
    assert "__lemur_probe_test1234" in output

    # Unwrap
    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "greeting", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, rel_path)
    assert "__lemur_probe_test1234" not in output
    assert "hello" in output


def test_unwrap_restores_numeric_rvalue(tmp_path: Path):
    """Instrument $x = 42 rvalue, then unwrap."""
    ast = parse_php(tmp_path, code='<?php\n$x = 42;\n')
    rhs = find_node(ast, "Scalar_LNumber")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_num")
    instrumenter.instrument_node(rhs.id, "x_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "x_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_num" not in output
    assert "42" in output


def test_unwrap_not_found_returns_false(tmp_path: Path):
    """Unwrapping nonexistent key returns False."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "nonexistent", ast)
    assert result is False


def test_unwrap_multiple_probes(tmp_path: Path):
    """Instrument two targets, unwrap both."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\necho "world";\n')
    strings = find_nodes(ast, "Scalar_String")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_multi")
    instrumenter.instrument_node(strings[0].id, "first")
    instrumenter.instrument_node(strings[1].id, "second")

    deinstrumenter = ASTDeinstrumenter()
    exclude: set[str] = set()
    assert deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "first", ast, exclude) is True
    assert deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "second", ast, exclude) is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_multi" not in output
    assert "hello" in output
    assert "world" in output


def test_unwrap_tracks_exclude_node_ids(tmp_path: Path):
    """Exclude set is populated after unwrap."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_exc")
    instrumenter.instrument_node(target.id, "greeting")

    exclude: set[str] = set()
    deinstrumenter = ASTDeinstrumenter()
    deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "greeting", ast, exclude)
    assert len(exclude) == 1


# --- _is_probe_call ---

def test_is_probe_call_detects_instrumented_node(tmp_path: Path):
    """_is_probe_call returns True for an instrumented FuncCall."""
    ast = parse_php(tmp_path, code='<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_detect")
    instrumenter.instrument_node(target.id, "greeting")

    func_calls = find_nodes(ast, "Expr_FuncCall")
    deinstrumenter = ASTDeinstrumenter()
    probe_calls = [fc for fc in func_calls if deinstrumenter._is_probe_call(ast, fc)]
    assert len(probe_calls) == 1


def test_is_probe_call_rejects_normal_function(tmp_path: Path):
    """_is_probe_call returns False for a normal function call."""
    ast = parse_php(tmp_path, code='<?php\nfoo("bar");\n')
    func_call = find_node(ast, "Expr_FuncCall")

    deinstrumenter = ASTDeinstrumenter()
    assert deinstrumenter._is_probe_call(ast, func_call) is False


def test_is_probe_call_rejects_method_call(tmp_path: Path):
    """_is_probe_call returns False for method calls (different node type)."""
    ast = parse_php(tmp_path, code='<?php\n$obj->method("x");\n')
    method_calls = find_nodes(ast, "Expr_MethodCall")
    assert len(method_calls) >= 1
    func_calls = find_nodes(ast, "Expr_FuncCall")
    deinstrumenter = ASTDeinstrumenter()
    for fc in func_calls:
        assert deinstrumenter._is_probe_call(ast, fc) is False


# --- scan_and_unwrap ---

def test_scan_and_unwrap_finds_instrumented_files(tmp_path: Path):
    """scan_and_unwrap processes PHP files with probes."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = parse_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    target = find_node(ast, "Scalar_String")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_scan")
    instrumenter.instrument_node(target.id, "greeting")

    # Write instrumented code to disk
    rel_path = ast.file_nodes()[0].get_property("relativePath")
    instrumented = PrettyPrinter().print_file(ast, rel_path)
    (tmp_path / "app.php").write_text(instrumented, encoding="utf-8")

    # Scan and unwrap
    deinstrumenter = ASTDeinstrumenter()
    modified = deinstrumenter.scan_and_unwrap(tmp_path)
    assert len(modified) == 1
    assert "__lemur_probe_scan" not in modified[0].read_text()


def test_scan_and_unwrap_skips_non_probe_files(tmp_path: Path):
    """scan_and_unwrap skips files without probe calls."""
    write_php(tmp_path, "clean.php", '<?php\necho "clean";\n')
    deinstrumenter = ASTDeinstrumenter()
    modified = deinstrumenter.scan_and_unwrap(tmp_path)
    assert modified == []


# --- unwrap_probe_ast: OOP constructs ---

def test_unwrap_restores_method_call(tmp_path: Path):
    """Instrument $obj->getStatus() rvalue, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\n$result = $obj->getStatus();\n')
    method_call = find_node(ast, "Expr_MethodCall")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_mc")
    instrumenter.instrument_node(method_call.id, "status")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "status", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_mc" not in output
    assert "getStatus" in output


def test_unwrap_restores_static_method_call(tmp_path: Path):
    """Instrument Foo::create() rvalue, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\n$obj = Foo::create();\n')
    static_call = find_node(ast, "Expr_StaticCall")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_sc")
    instrumenter.instrument_node(static_call.id, "create")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "create", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_sc" not in output
    assert "Foo" in output
    assert "create" in output


def test_unwrap_restores_property_fetch(tmp_path: Path):
    """Instrument $obj->name in echo, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\necho $obj->name;\n')
    prop = find_node(ast, "Expr_PropertyFetch")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_pf")
    instrumenter.instrument_node(prop.id, "name_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "name_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_pf" not in output
    assert "name" in output


def test_unwrap_restores_new_instance(tmp_path: Path):
    """Instrument new Foo() rvalue, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\n$obj = new Foo();\n')
    new_expr = find_node(ast, "Expr_New")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_nw")
    instrumenter.instrument_node(new_expr.id, "new_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "new_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_nw" not in output
    assert "new" in output
    assert "Foo" in output


# --- unwrap_probe_ast: complex expressions ---

def test_unwrap_restores_null_coalesce(tmp_path: Path):
    """Instrument $a ?? $b, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\n$result = $a ?? $b;\n')
    coalesce = find_node(ast, "Expr_BinaryOp_Coalesce")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_nc")
    instrumenter.instrument_node(coalesce.id, "coal_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "coal_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_nc" not in output
    assert "??" in output


def test_unwrap_restores_cast_expression(tmp_path: Path):
    """Instrument (int)$x, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\n$val = (int)$x;\n')
    cast = find_node(ast, "Expr_Cast_Int")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_ct")
    instrumenter.instrument_node(cast.id, "cast_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "cast_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_ct" not in output
    assert "(int)" in output


def test_unwrap_restores_instanceof(tmp_path: Path):
    """Instrument $x instanceof Foo, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\n$check = $x instanceof Foo;\n')
    instanceof = find_node(ast, "Expr_Instanceof")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_io")
    instrumenter.instrument_node(instanceof.id, "inst_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "inst_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_io" not in output
    assert "instanceof" in output


def test_unwrap_restores_closure(tmp_path: Path):
    """Instrument closure, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\narray_map(function($x) { return $x * 2; }, $arr);\n')
    closure = find_node(ast, "Expr_Closure")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_cl")
    instrumenter.instrument_node(closure.id, "cls_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "cls_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_cl" not in output
    assert "function" in output


def test_unwrap_restores_arrow_function(tmp_path: Path):
    """Instrument arrow function, then unwrap restores original."""
    ast = parse_php(tmp_path, code='<?php\n$fn = fn($x) => $x + 1;\n')
    arrow = find_node(ast, "Expr_ArrowFunction")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_af")
    instrumenter.instrument_node(arrow.id, "arrow_val")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "arrow_val", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_af" not in output
    assert "fn" in output


# --- unwrap_probe_ast: complex structures ---

def test_unwrap_restores_class_method_expression(tmp_path: Path):
    """Instrument expression inside class method, then unwrap restores."""
    code = '<?php\nclass Calc {\n    public function add($a, $b) {\n        return $a + $b;\n    }\n}\n'
    ast = parse_php(tmp_path, code=code)
    plus = find_node(ast, "Expr_BinaryOp_Plus")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_cm")
    instrumenter.instrument_node(plus.id, "add_op")

    deinstrumenter = ASTDeinstrumenter()
    result = deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "add_op", ast)
    assert result is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_cm" not in output
    assert "class Calc" in output


def test_unwrap_multiple_probes_complex_code(tmp_path: Path):
    """Instrument multiple targets in complex code, unwrap all."""
    code = '<?php\nclass Svc {\n    public function run($x) {\n        $a = $x + 1;\n        return $a * 2;\n    }\n}\n'
    ast = parse_php(tmp_path, code=code)
    plus = find_node(ast, "Expr_BinaryOp_Plus")
    mul = find_node(ast, "Expr_BinaryOp_Mul")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_mc")
    instrumenter.instrument_node(plus.id, "add_op")
    instrumenter.instrument_node(mul.id, "mul_op")

    deinstrumenter = ASTDeinstrumenter()
    exclude: set[str] = set()
    assert deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "add_op", ast, exclude) is True
    assert deinstrumenter.unwrap_probe_ast(tmp_path / "test.php", "mul_op", ast, exclude) is True

    output = PrettyPrinter().print_file(ast, ast.file_nodes()[0].get_property("relativePath"))
    assert "__lemur_probe_mc" not in output
    assert "class Svc" in output


# --- _is_probe_call: complex scenarios ---

def test_is_probe_call_rejects_static_method_call(tmp_path: Path):
    """_is_probe_call returns False for static method calls."""
    ast = parse_php(tmp_path, code='<?php\nFoo::bar("x");\n')
    static_calls = find_nodes(ast, "Expr_StaticCall")
    assert len(static_calls) >= 1
    func_calls = find_nodes(ast, "Expr_FuncCall")
    deinstrumenter = ASTDeinstrumenter()
    for fc in func_calls:
        assert deinstrumenter._is_probe_call(ast, fc) is False


def test_is_probe_call_distinguishes_probe_among_normal_calls(tmp_path: Path):
    """_is_probe_call only matches probe calls when mixed with normal calls."""
    ast = parse_php(tmp_path, code='<?php\nfoo("bar");\necho "hello";\n')
    target = find_node(ast, "Scalar_String", value="hello")

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_mix")
    instrumenter.instrument_node(target.id, "greeting")

    func_calls = find_nodes(ast, "Expr_FuncCall")
    deinstrumenter = ASTDeinstrumenter()
    probe_calls = [fc for fc in func_calls if deinstrumenter._is_probe_call(ast, fc)]
    non_probe_calls = [fc for fc in func_calls if not deinstrumenter._is_probe_call(ast, fc)]
    assert len(probe_calls) == 1
    assert len(non_probe_calls) >= 1


# --- scan_and_unwrap: complex scenarios ---

def test_scan_and_unwrap_multiple_files(tmp_path: Path):
    """scan_and_unwrap processes multiple instrumented PHP files."""
    for name in ("a.php", "b.php"):
        write_php(tmp_path, name, f'<?php\necho "{name}";\n')
        ast = parse_php(tmp_path, name, f'<?php\necho "{name}";\n')
        target = find_node(ast, "Scalar_String")
        instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_mf")
        instrumenter.instrument_node(target.id, f"key_{name}")
        rel_path = ast.file_nodes()[0].get_property("relativePath")
        instrumented = PrettyPrinter().print_file(ast, rel_path)
        (tmp_path / name).write_text(instrumented, encoding="utf-8")

    deinstrumenter = ASTDeinstrumenter()
    modified = deinstrumenter.scan_and_unwrap(tmp_path)
    assert len(modified) == 2
    for f in modified:
        assert "__lemur_probe_mf" not in f.read_text()


def test_scan_and_unwrap_mixed_clean_and_instrumented(tmp_path: Path):
    """scan_and_unwrap only modifies instrumented files, skips clean ones."""
    write_php(tmp_path, "clean.php", '<?php\necho "clean";\n')

    write_php(tmp_path, "dirty.php", '<?php\necho "dirty";\n')
    ast = parse_php(tmp_path, "dirty.php", '<?php\necho "dirty";\n')
    target = find_node(ast, "Scalar_String")
    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_mix")
    instrumenter.instrument_node(target.id, "dirty_key")
    rel_path = ast.file_nodes()[0].get_property("relativePath")
    instrumented = PrettyPrinter().print_file(ast, rel_path)
    (tmp_path / "dirty.php").write_text(instrumented, encoding="utf-8")

    deinstrumenter = ASTDeinstrumenter()
    modified = deinstrumenter.scan_and_unwrap(tmp_path)
    assert len(modified) == 1
    assert modified[0].name == "dirty.php"


def test_scan_and_unwrap_complex_class_code(tmp_path: Path):
    """scan_and_unwrap handles class code with multiple probes."""
    code = '<?php\nclass User {\n    public function getName() {\n        return $this->first . " " . $this->last;\n    }\n}\n'
    write_php(tmp_path, "user.php", code)
    ast = parse_php(tmp_path, "user.php", code)
    concat_nodes = find_nodes(ast, "Expr_BinaryOp_Concat")
    assert len(concat_nodes) >= 1

    instrumenter = ASTInstrumenter(ast, StandardProbeStrategy(), "__lemur_probe_usr")
    instrumenter.instrument_node(concat_nodes[0].id, "name_concat")
    rel_path = ast.file_nodes()[0].get_property("relativePath")
    instrumented = PrettyPrinter().print_file(ast, rel_path)
    (tmp_path / "user.php").write_text(instrumented, encoding="utf-8")

    deinstrumenter = ASTDeinstrumenter()
    modified = deinstrumenter.scan_and_unwrap(tmp_path)
    assert len(modified) == 1
    content = modified[0].read_text()
    assert "__lemur_probe_usr" not in content
    assert "class User" in content
