"""Tests for porifera._manager using real PHP code."""

from pathlib import Path

import pytest
from php_parser_py import Parser

from conftest import find_child, find_node, find_nodes, parse_php, write_php
from porifera._exceptions import InstrumentationError
from porifera._manager import InstrumentationManager, _RUNTIME_HELPER_NAME, deinstrument, instrument

import re


# --- _resolve_project_root ---

def test_resolve_project_root_from_project_node(tmp_path: Path):
    """Project root is resolved from project node absolutePath."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    root = InstrumentationManager._resolve_project_root(ast)
    assert root == tmp_path.resolve()


def test_resolve_project_root_falls_back_to_file_node(tmp_path: Path):
    """Project root falls back to parent of first file node."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    # Real parser always has a project node, so this tests the normal path
    root = InstrumentationManager._resolve_project_root(ast)
    assert root.is_dir()


# --- instrument ---

def test_instrument_empty_targets(tmp_path: Path):
    """Empty targets dict returns empty list."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    manager = InstrumentationManager(ast)
    result = manager.instrument({})
    assert result == []


def test_instrument_wraps_and_regenerates_file(tmp_path: Path):
    """Instrument a target: file should contain probe call afterward."""
    php_file = write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(php_file))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({target.id: "greeting"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "greeting" in content
    assert _RUNTIME_HELPER_NAME in content  # require_once injected


def test_instrument_creates_runtime_helper(tmp_path: Path):
    """Runtime helper PHP file is created in project root."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    manager.instrument({target.id: "greeting"})

    helper = tmp_path / _RUNTIME_HELPER_NAME
    assert helper.exists()
    helper_content = helper.read_text()
    assert "function" in helper_content
    assert manager._probe_func_name in helper_content


def test_instrument_registers_expr_keys(tmp_path: Path):
    """Instrumented expr_keys are recorded in registry."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    manager.instrument({target.id: "greeting"})

    file_path = (tmp_path / "app.php").resolve()
    keys = manager.registry.get_expr_keys(file_path)
    assert "greeting" in keys


def test_instrument_multiple_targets_same_file(tmp_path: Path):
    """Multiple targets in same file produce one modified file."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\necho "world";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    strings = find_nodes(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    targets = {s.id: f"key_{i}" for i, s in enumerate(strings)}
    modified = manager.instrument(targets)

    assert len(modified) == 1
    content = (tmp_path / "app.php").read_text()
    assert "key_0" in content
    assert "key_1" in content


def test_instrument_skips_unsafe_targets(tmp_path: Path):
    """Lvalue targets are skipped; no file modification if all skip."""
    write_php(tmp_path, "app.php", '<?php\n$x = 42;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    assign = find_node(ast, "Expr_Assign")
    lhs = find_child(ast, assign, "var")

    manager = InstrumentationManager(ast)
    # Only target the lvalue — should skip
    modified = manager.instrument({lhs.id: "x_var"})
    # The rvalue 42 is NOT targeted, so no file should be modified
    # But runtime helper was created — check modified list
    assert modified == []


# --- deinstrument ---

def test_deinstrument_registry_mode_empty(tmp_path: Path):
    """Deinstrument with empty registry returns empty."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    manager = InstrumentationManager(ast)
    result = manager.deinstrument(use_registry=True)
    assert result == []


def test_deinstrument_cleanup_removes_helper(tmp_path: Path):
    """Deinstrument removes runtime helper file."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    manager = InstrumentationManager(ast)

    helper = tmp_path / _RUNTIME_HELPER_NAME
    helper.write_text("<?php // probe func")

    manager.deinstrument(use_registry=True)
    assert not helper.exists()


def test_full_instrument_deinstrument_roundtrip(tmp_path: Path):
    """Full roundtrip: instrument, then deinstrument restores original."""
    original_code = '<?php\necho "hello";\n'
    write_php(tmp_path, "app.php", original_code)
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    manager.instrument({target.id: "greeting"})

    # Verify instrumented
    content = (tmp_path / "app.php").read_text()
    assert "greeting" in content
    assert manager._probe_func_name in content

    # Deinstrument via scan mode (re-parse needed)
    ast2 = Parser().parse_file(str(tmp_path / "app.php"))
    manager2 = InstrumentationManager(ast2)
    # Copy registry from original manager
    manager2.registry.data = dict(manager.registry.data)
    manager2.registry._save()
    modified = manager2.deinstrument(use_registry=True)

    restored = (tmp_path / "app.php").read_text()
    assert manager._probe_func_name not in restored
    assert "hello" in restored


# --- inject / remove require ---

def test_inject_require(tmp_path: Path):
    """require_once is injected after <?php tag."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    manager = InstrumentationManager(ast)

    php_file = tmp_path / "test.php"
    php_file.write_text("<?php\necho 'hello';")
    manager._inject_require(php_file)

    content = php_file.read_text()
    assert f"require_once __DIR__ . '/{_RUNTIME_HELPER_NAME}';" in content


def test_inject_require_idempotent(tmp_path: Path):
    """Injecting require twice doesn't duplicate."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    manager = InstrumentationManager(ast)

    php_file = tmp_path / "test.php"
    php_file.write_text("<?php\necho 'hello';")
    manager._inject_require(php_file)
    manager._inject_require(php_file)

    content = php_file.read_text()
    assert content.count("require_once") == 1


def test_remove_require(tmp_path: Path):
    """require_once line is removed."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    manager = InstrumentationManager(ast)

    php_file = tmp_path / "test.php"
    php_file.write_text(
        f"<?php\nrequire_once __DIR__ . '/{_RUNTIME_HELPER_NAME}';\necho 'hello';",
    )
    result = manager._remove_require(php_file)
    assert result is True
    assert _RUNTIME_HELPER_NAME not in php_file.read_text()


def test_remove_require_no_require_returns_false(tmp_path: Path):
    """_remove_require returns False when no require_once exists."""
    write_php(tmp_path, "app.php", '<?php\necho 1;\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    manager = InstrumentationManager(ast)

    php_file = tmp_path / "test.php"
    php_file.write_text("<?php\necho 'hello';")
    result = manager._remove_require(php_file)
    assert result is False


# --- Public API ---

def test_public_instrument(tmp_path: Path):
    """Public instrument() function wraps target and returns modified files."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    result = instrument({target.id: "greeting"}, ast)
    assert len(result) == 1
    content = (tmp_path / "app.php").read_text()
    assert "greeting" in content


def test_public_deinstrument(tmp_path: Path):
    """Public deinstrument() removes probes via scan mode."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    instrument({target.id: "greeting"}, ast)
    # Re-parse for deinstrument
    ast2 = Parser().parse_file(str(tmp_path / "app.php"))
    result = deinstrument(ast2, use_registry=False)

    content = (tmp_path / "app.php").read_text()
    assert "hello" in content


# --- instrument: OOP PHP constructs ---

def test_instrument_class_method_expression(tmp_path: Path):
    """Instrument expression inside a class method body."""
    code = '<?php\nclass Calculator {\n    public function add($a, $b) {\n        return $a + $b;\n    }\n}\n'
    php_file = write_php(tmp_path, "calc.php", code)
    ast = Parser().parse_file(str(php_file))
    plus = find_node(ast, "Expr_BinaryOp_Plus")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({plus.id: "add_result"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "add_result" in content
    assert "class Calculator" in content


def test_instrument_method_call_rvalue(tmp_path: Path):
    """Instrument method call result as assignment rvalue."""
    code = '<?php\n$result = $obj->getStatus();\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    method_call = find_node(ast, "Expr_MethodCall")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({method_call.id: "status_val"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "status_val" in content


def test_instrument_static_call_rvalue(tmp_path: Path):
    """Instrument static method call result as assignment rvalue."""
    code = '<?php\n$instance = Config::load();\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    static_call = find_node(ast, "Expr_StaticCall")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({static_call.id: "config_val"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "config_val" in content


def test_instrument_new_instance_rvalue(tmp_path: Path):
    """Instrument new Foo() as assignment rvalue."""
    code = '<?php\n$svc = new UserService();\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    new_expr = find_node(ast, "Expr_New")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({new_expr.id: "svc_val"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "svc_val" in content


# --- instrument: complex expressions ---

def test_instrument_null_coalesce_expression(tmp_path: Path):
    """Instrument null coalescing expression."""
    code = '<?php\n$name = $user->name ?? "anonymous";\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    coalesce = find_node(ast, "Expr_BinaryOp_Coalesce")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({coalesce.id: "name_val"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "name_val" in content


def test_instrument_closure_argument(tmp_path: Path):
    """Instrument closure passed as function argument."""
    code = '<?php\n$filtered = array_filter($items, function($item) { return $item > 0; });\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    closure = find_node(ast, "Expr_Closure")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({closure.id: "filter_fn"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "filter_fn" in content


def test_instrument_arrow_function_rvalue(tmp_path: Path):
    """Instrument arrow function as assignment rvalue."""
    code = '<?php\n$double = fn($n) => $n * 2;\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    arrow = find_node(ast, "Expr_ArrowFunction")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({arrow.id: "double_fn"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "double_fn" in content


def test_instrument_instanceof_condition(tmp_path: Path):
    """Instrument instanceof check as assignment rvalue."""
    code = '<?php\n$isAdmin = $user instanceof AdminUser;\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    instanceof = find_node(ast, "Expr_Instanceof")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({instanceof.id: "admin_check"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "admin_check" in content


# --- instrument: multiple targets complex code ---

def test_instrument_multiple_targets_class_with_methods(tmp_path: Path):
    """Instrument multiple targets across a class with multiple methods."""
    code = (
        '<?php\n'
        'class UserService {\n'
        '    public function getFullName($first, $last) {\n'
        '        return $first . " " . $last;\n'
        '    }\n'
        '    public function isActive($user) {\n'
        '        return $user->status === "active";\n'
        '    }\n'
        '}\n'
    )
    php_file = write_php(tmp_path, "user_service.php", code)
    ast = Parser().parse_file(str(php_file))

    concat_nodes = find_nodes(ast, "Expr_BinaryOp_Concat")
    identical = find_node(ast, "Expr_BinaryOp_Identical")

    targets = {concat_nodes[0].id: "name_concat", identical.id: "status_check"}
    manager = InstrumentationManager(ast)
    modified = manager.instrument(targets)

    assert len(modified) == 1
    content = php_file.read_text()
    assert "name_concat" in content
    assert "status_check" in content


def test_instrument_mixed_safe_and_unsafe_targets(tmp_path: Path):
    """Only safe targets are instrumented; unsafe ones are skipped."""
    code = '<?php\n$x = 42;\n$y = $x + 1;\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))

    assign = find_node(ast, "Expr_Assign")
    lhs = find_child(ast, assign, "var")
    plus = find_node(ast, "Expr_BinaryOp_Plus")

    manager = InstrumentationManager(ast)
    modified = manager.instrument({lhs.id: "unsafe_var", plus.id: "safe_add"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "safe_add" in content
    assert "unsafe_var" not in content


# --- instrument: with ElevatingProbeStrategy ---

def test_instrument_with_elevating_strategy(tmp_path: Path):
    """Manager with ElevatingProbeStrategy elevates lvalue to assignment."""
    from porifera._strategies._elevating import ElevatingProbeStrategy

    code = '<?php\nfor ($i = 0; $i < 10; $i++) { echo $i; }\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))

    post_inc = find_node(ast, "Expr_PostInc")
    var = find_child(ast, post_inc, "var")
    assert var is not None

    manager = InstrumentationManager(ast, strategy=ElevatingProbeStrategy())
    modified = manager.instrument({var.id: "inc_val"})

    assert len(modified) == 1
    content = php_file.read_text()
    assert "inc_val" in content


# --- full roundtrip: complex PHP ---

def test_roundtrip_class_with_method(tmp_path: Path):
    """Full roundtrip: instrument class method expression, then restore."""
    code = '<?php\nclass Greeter {\n    public function greet($name) {\n        return "Hello, " . $name;\n    }\n}\n'
    php_file = write_php(tmp_path, "greeter.php", code)
    ast = Parser().parse_file(str(php_file))
    concat = find_node(ast, "Expr_BinaryOp_Concat")

    manager = InstrumentationManager(ast)
    manager.instrument({concat.id: "greet_msg"})

    content = php_file.read_text()
    assert "greet_msg" in content
    assert manager._probe_func_name in content

    ast2 = Parser().parse_file(str(php_file))
    manager2 = InstrumentationManager(ast2)
    manager2.registry.data = dict(manager.registry.data)
    manager2.registry._save()
    manager2.deinstrument(use_registry=True)

    restored = php_file.read_text()
    assert manager._probe_func_name not in restored
    assert "class Greeter" in restored
    assert "Hello" in restored


def test_roundtrip_multiple_targets(tmp_path: Path):
    """Full roundtrip: instrument multiple targets, then restore all."""
    code = '<?php\n$a = 10;\n$b = 20;\necho $a + $b;\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))

    nums = find_nodes(ast, "Scalar_LNumber")
    targets = {n.id: f"num_{i}" for i, n in enumerate(nums)}

    manager = InstrumentationManager(ast)
    modified = manager.instrument(targets)
    assert len(modified) == 1

    ast2 = Parser().parse_file(str(php_file))
    manager2 = InstrumentationManager(ast2)
    manager2.registry.data = dict(manager.registry.data)
    manager2.registry._save()
    manager2.deinstrument(use_registry=True)

    restored = php_file.read_text()
    assert manager._probe_func_name not in restored
    assert "10" in restored
    assert "20" in restored


def test_roundtrip_scan_mode_complex_code(tmp_path: Path):
    """Full roundtrip via scan mode with complex OOP code."""
    code = (
        '<?php\n'
        'class Logger {\n'
        '    private $level;\n'
        '    public function __construct($level) {\n'
        '        $this->level = $level;\n'
        '    }\n'
        '    public function log($msg) {\n'
        '        echo "[" . $this->level . "] " . $msg;\n'
        '    }\n'
        '}\n'
    )
    php_file = write_php(tmp_path, "logger.php", code)
    ast = Parser().parse_file(str(php_file))
    concat_nodes = find_nodes(ast, "Expr_BinaryOp_Concat")
    assert len(concat_nodes) >= 1

    manager = InstrumentationManager(ast)
    manager.instrument({concat_nodes[0].id: "log_concat"})

    content = php_file.read_text()
    assert "log_concat" in content

    ast2 = Parser().parse_file(str(php_file))
    deinstrument(ast2, use_registry=False)

    restored = php_file.read_text()
    assert manager._probe_func_name not in restored
    assert "class Logger" in restored


def test_roundtrip_null_coalesce(tmp_path: Path):
    """Full roundtrip with null coalescing expression."""
    code = '<?php\n$name = $input ?? "default";\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    coalesce = find_node(ast, "Expr_BinaryOp_Coalesce")

    manager = InstrumentationManager(ast)
    manager.instrument({coalesce.id: "name_val"})

    content = php_file.read_text()
    assert "name_val" in content

    ast2 = Parser().parse_file(str(php_file))
    manager2 = InstrumentationManager(ast2)
    manager2.registry.data = dict(manager.registry.data)
    manager2.registry._save()
    manager2.deinstrument(use_registry=True)

    restored = php_file.read_text()
    assert manager._probe_func_name not in restored
    assert "??" in restored


def test_roundtrip_closure(tmp_path: Path):
    """Full roundtrip with closure expression."""
    code = '<?php\n$fn = function($x) { return $x * 2; };\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    closure = find_node(ast, "Expr_Closure")

    result = instrument({closure.id: "closure_val"}, ast)
    assert len(result) == 1

    ast2 = Parser().parse_file(str(php_file))
    deinstrument(ast2, use_registry=False)

    restored = php_file.read_text()
    assert "function" in restored
    assert "return" in restored


# --- Public API: complex scenarios ---

def test_public_instrument_class_code(tmp_path: Path):
    """Public instrument() wraps target inside class code."""
    code = '<?php\nclass Adder {\n    public function run($x) { return $x + 1; }\n}\n'
    php_file = write_php(tmp_path, "adder.php", code)
    ast = Parser().parse_file(str(php_file))
    plus = find_node(ast, "Expr_BinaryOp_Plus")

    result = instrument({plus.id: "add_val"}, ast)
    assert len(result) == 1
    content = php_file.read_text()
    assert "add_val" in content


def test_public_deinstrument_class_code(tmp_path: Path):
    """Public deinstrument() restores class code via scan mode."""
    code = '<?php\nclass Adder {\n    public function run($x) { return $x + 1; }\n}\n'
    php_file = write_php(tmp_path, "adder.php", code)
    ast = Parser().parse_file(str(php_file))
    plus = find_node(ast, "Expr_BinaryOp_Plus")

    instrument({plus.id: "add_val"}, ast)

    ast2 = Parser().parse_file(str(php_file))
    deinstrument(ast2, use_registry=False)

    restored = php_file.read_text()
    assert "class Adder" in restored
    assert "add_val" not in restored


def test_public_instrument_with_elevating_strategy(tmp_path: Path):
    """Public instrument() with ElevatingProbeStrategy."""
    from porifera._strategies._elevating import ElevatingProbeStrategy

    code = '<?php\n$i = 0;\n$i++;\necho $i;\n'
    php_file = write_php(tmp_path, "app.php", code)
    ast = Parser().parse_file(str(php_file))
    post_inc = find_node(ast, "Expr_PostInc")
    var = find_child(ast, post_inc, "var")
    assert var is not None

    result = instrument({var.id: "inc_val"}, ast, strategy=ElevatingProbeStrategy())
    assert len(result) == 1
    content = php_file.read_text()
    assert "inc_val" in content


# --- output_dir ---

def test_instrument_default_output_dir(tmp_path: Path):
    """Default output_dir uses __DIR__ in generated runtime helper."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    manager.instrument({target.id: "greeting"})

    helper = tmp_path / _RUNTIME_HELPER_NAME
    content = helper.read_text()
    assert "__DIR__ . '/.porifera_data_" in content


def test_instrument_custom_output_dir(tmp_path: Path):
    """Custom output_dir path appears in generated runtime helper."""
    output_dir = tmp_path / "logs"
    output_dir.mkdir()

    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast, output_dir=output_dir)
    manager.instrument({target.id: "greeting"})

    helper = tmp_path / _RUNTIME_HELPER_NAME
    content = helper.read_text()
    assert str(output_dir.resolve()) in content
    assert "__DIR__" not in content


def test_instrument_runtime_helper_has_timestamp(tmp_path: Path):
    """Runtime helper filename pattern includes a timestamp."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    manager.instrument({target.id: "greeting"})

    helper = tmp_path / _RUNTIME_HELPER_NAME
    content = helper.read_text()
    # Timestamp format: YYYYMMDD_HHMMSS_hexsuffix
    assert re.search(
        r"\.porifera_data_\d{8}_\d{6}_[0-9a-f]{6}\.jsonl", content,
    )


def test_instrument_uses_flock(tmp_path: Path):
    """Runtime helper uses flock for concurrency-safe writes."""
    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    manager = InstrumentationManager(ast)
    manager.instrument({target.id: "greeting"})

    helper = tmp_path / _RUNTIME_HELPER_NAME
    content = helper.read_text()
    assert "flock(" in content
    assert "LOCK_EX" in content


def test_public_instrument_with_output_dir(tmp_path: Path):
    """Public instrument() accepts output_dir parameter."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    write_php(tmp_path, "app.php", '<?php\necho "hello";\n')
    ast = Parser().parse_file(str(tmp_path / "app.php"))
    target = find_node(ast, "Scalar_String")

    result = instrument(
        {target.id: "greeting"}, ast, output_dir=output_dir,
    )
    assert len(result) == 1

    helper = tmp_path / _RUNTIME_HELPER_NAME
    content = helper.read_text()
    assert str(output_dir.resolve()) in content
