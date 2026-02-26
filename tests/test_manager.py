"""Tests for lemur._manager."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conftest import FakeAST, FakeNode, build_parent_child
from lemur._exceptions import DeinstrumentationError, InstrumentationError
from lemur._manager import InstrumentationManager, _RUNTIME_HELPER_NAME, deinstrument, instrument


def _build_project_ast(project_root: Path) -> FakeAST:
    """Build a minimal project AST with project node and one file node."""
    ast = FakeAST()

    project_node = FakeNode("project", "Project", absolutePath=str(project_root))
    file_node = FakeNode(
        "file1", "File",
        absolutePath=str(project_root / "app.php"),
        relativePath="app.php",
    )
    target_node = FakeNode("node1", "Scalar_String", value="hello", startLine=1, endLine=1)

    ast._nodes = {n.id: n for n in [project_node, file_node, target_node]}
    ast._project = project_node
    ast._files = [file_node]

    build_parent_child(ast, project_node, file_node, field="files", index=0)
    build_parent_child(ast, file_node, target_node, field="stmts", index=0)

    return ast


# --- _resolve_project_root ---

def test_resolve_project_root_from_project_node(tmp_path: Path):
    ast = FakeAST()
    project_node = FakeNode("project", "Project", absolutePath=str(tmp_path))
    ast._project = project_node
    ast._nodes = {"project": project_node}

    root = InstrumentationManager._resolve_project_root(ast)
    assert root == tmp_path.resolve()


def test_resolve_project_root_falls_back_to_file_node(tmp_path: Path):
    ast = FakeAST()
    # project_node raises KeyError (no project)
    php_file = tmp_path / "app.php"
    php_file.write_text("<?php echo 1;")
    file_node = FakeNode("file1", "File", absolutePath=str(php_file))
    ast._files = [file_node]
    ast._nodes = {"file1": file_node}

    root = InstrumentationManager._resolve_project_root(ast)
    assert root == tmp_path.resolve()


def test_resolve_project_root_raises_when_no_path():
    ast = FakeAST()
    with pytest.raises(InstrumentationError, match="Could not resolve project root"):
        InstrumentationManager._resolve_project_root(ast)


# --- instrument ---

@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_instrument_empty_targets_returns_empty(tmp_path: Path):
    ast = _build_project_ast(tmp_path)
    manager = InstrumentationManager(ast)
    result = manager.instrument({})
    assert result == []


@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_instrument_creates_runtime_helper(tmp_path: Path):
    ast = _build_project_ast(tmp_path)

    # Mock the instrumenter to return True
    manager = InstrumentationManager(ast)
    manager._instrumenter = MagicMock()
    manager._instrumenter.instrument_node.return_value = True

    # Mock file regeneration
    manager._regenerate_file = MagicMock()
    manager._inject_require = MagicMock()

    manager.instrument({"node1": "greeting"})

    helper_path = tmp_path / _RUNTIME_HELPER_NAME
    assert helper_path.exists()


@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_instrument_registers_expr_keys(tmp_path: Path):
    ast = _build_project_ast(tmp_path)
    manager = InstrumentationManager(ast)
    manager._instrumenter = MagicMock()
    manager._instrumenter.instrument_node.return_value = True
    manager._regenerate_file = MagicMock()
    manager._inject_require = MagicMock()

    manager.instrument({"node1": "greeting"})

    file_path = Path(str(tmp_path / "app.php")).resolve()
    keys = manager.registry.get_expr_keys(file_path)
    assert "greeting" in keys


# --- deinstrument ---

@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_deinstrument_registry_mode(tmp_path: Path):
    ast = _build_project_ast(tmp_path)
    manager = InstrumentationManager(ast)
    # No registered files, should return empty
    result = manager.deinstrument(use_registry=True)
    assert result == []


@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_deinstrument_cleanup_removes_helper(tmp_path: Path):
    ast = _build_project_ast(tmp_path)
    manager = InstrumentationManager(ast)

    # Create runtime helper file
    helper_path = tmp_path / _RUNTIME_HELPER_NAME
    helper_path.write_text("<?php // probe func")

    manager.deinstrument(use_registry=True)
    assert not helper_path.exists()


# --- inject / remove require ---

@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_inject_require(tmp_path: Path):
    ast = _build_project_ast(tmp_path)
    manager = InstrumentationManager(ast)

    php_file = tmp_path / "test.php"
    php_file.write_text("<?php\necho 'hello';")

    manager._inject_require(php_file)

    content = php_file.read_text()
    assert f"require_once __DIR__ . '/{_RUNTIME_HELPER_NAME}';" in content


@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_inject_require_idempotent(tmp_path: Path):
    ast = _build_project_ast(tmp_path)
    manager = InstrumentationManager(ast)

    php_file = tmp_path / "test.php"
    php_file.write_text("<?php\necho 'hello';")

    manager._inject_require(php_file)
    manager._inject_require(php_file)

    content = php_file.read_text()
    assert content.count("require_once") == 1


@patch("lemur._operations._instrumenter.Modifier", new=MagicMock())
def test_remove_require(tmp_path: Path):
    ast = _build_project_ast(tmp_path)
    manager = InstrumentationManager(ast)

    php_file = tmp_path / "test.php"
    php_file.write_text(
        f"<?php\nrequire_once __DIR__ . '/{_RUNTIME_HELPER_NAME}';\necho 'hello';",
    )

    result = manager._remove_require(php_file)
    assert result is True
    assert _RUNTIME_HELPER_NAME not in php_file.read_text()


# --- Public API ---

@patch("lemur._manager.InstrumentationManager")
def test_public_instrument_delegates(mock_cls: MagicMock):
    mock_instance = MagicMock()
    mock_instance.instrument.return_value = [Path("/a.php")]
    mock_cls.return_value = mock_instance

    ast = MagicMock()
    result = instrument({"n1": "key"}, ast)
    assert result == [Path("/a.php")]
    mock_cls.assert_called_once_with(ast, None)


@patch("lemur._manager.InstrumentationManager")
def test_public_deinstrument_delegates(mock_cls: MagicMock):
    mock_instance = MagicMock()
    mock_instance.deinstrument.return_value = [Path("/a.php")]
    mock_cls.return_value = mock_instance

    ast = MagicMock()
    result = deinstrument(ast, use_registry=False)
    assert result == [Path("/a.php")]
    mock_instance.deinstrument.assert_called_once_with(False)
