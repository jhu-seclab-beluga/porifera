"""Tests for porifera._registry."""

import json
from pathlib import Path

import pytest

from porifera._registry import InstrumentationRegistry


@pytest.fixture()
def registry_path(tmp_path: Path) -> Path:
    """Return a fresh registry file path under tmp_path."""
    return tmp_path / ".porifera_registry.json"


def test_init_empty(registry_path: Path):
    """New registry has no data and no file on disk."""
    reg = InstrumentationRegistry(registry_path)
    assert reg.data == {}
    assert not registry_path.exists()


def test_init_loads_existing(registry_path: Path):
    """Registry loads data from existing JSON file."""
    data = {"/some/file.php": ["total", "count"]}
    registry_path.write_text(json.dumps(data))
    reg = InstrumentationRegistry(registry_path)
    assert reg.data == data


def test_register_appends_expr_key(registry_path: Path):
    """register() appends expr keys for the given file."""
    reg = InstrumentationRegistry(registry_path)
    file_path = Path("/project/src/app.php")
    reg.register(file_path, "total")
    reg.register(file_path, "count")
    key = str(file_path.resolve())
    assert reg.data[key] == ["total", "count"]


def test_register_persists_to_disk(registry_path: Path):
    """register() writes data to disk."""
    reg = InstrumentationRegistry(registry_path)
    reg.register(Path("/project/src/app.php"), "total")
    assert registry_path.exists()
    on_disk = json.loads(registry_path.read_text())
    assert len(on_disk) == 1


def test_atomic_write_uses_temp_file(registry_path: Path, tmp_path: Path):
    """Atomic save cleans up temp file after write."""
    reg = InstrumentationRegistry(registry_path)
    reg.register(Path("/a.php"), "x")
    # After save, temp file should be cleaned up
    temp = registry_path.with_suffix(".json.tmp")
    assert not temp.exists()
    assert registry_path.exists()


def test_get_expr_keys_returns_correct_keys(registry_path: Path):
    """get_expr_keys() returns registered keys for a file."""
    reg = InstrumentationRegistry(registry_path)
    fp = Path("/project/app.php")
    reg.register(fp, "a")
    reg.register(fp, "b")
    assert reg.get_expr_keys(fp) == ["a", "b"]


def test_get_expr_keys_unknown_file_returns_empty(registry_path: Path):
    """get_expr_keys() returns empty list for unknown file."""
    reg = InstrumentationRegistry(registry_path)
    assert reg.get_expr_keys(Path("/nonexistent.php")) == []


def test_get_all_files(registry_path: Path):
    """get_all_files() returns all registered file paths."""
    reg = InstrumentationRegistry(registry_path)
    fp1 = Path("/a.php")
    fp2 = Path("/b.php")
    reg.register(fp1, "x")
    reg.register(fp2, "y")
    all_files = reg.get_all_files()
    assert len(all_files) == 2


def test_clear_removes_all(registry_path: Path):
    """clear() removes all data and deletes the file."""
    reg = InstrumentationRegistry(registry_path)
    reg.register(Path("/a.php"), "x")
    assert registry_path.exists()
    reg.clear()
    assert not registry_path.exists()
    assert reg.data == {}
