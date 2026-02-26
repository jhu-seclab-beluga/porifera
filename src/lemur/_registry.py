"""Instrumentation registry for persisting state to .lemur_registry.json."""

import json
from pathlib import Path


class InstrumentationRegistry:
    """Persists instrumentation state for precise restoration during deinstrumentation.

    Attributes:
        registry_path: Path to the registry JSON file.
        data: Maps file paths to lists of expr_key strings.
    """

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        self.data: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        """Load registry from disk if it exists."""
        if not self.registry_path.exists():
            return
        with open(self.registry_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def _save(self) -> None:
        """Save registry to disk atomically (write-then-rename)."""
        temp_path = self.registry_path.with_suffix(".json.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        temp_path.replace(self.registry_path)

    def register(self, file_path: Path, expr_key: str) -> None:
        """Append an expr_key to the file's list and persist to disk.

        Args:
            file_path: Path to modified file.
            expr_key: Probe label for the instrumented expression.

        Raises:
            OSError: On write failure.
        """
        key = str(file_path.resolve())
        if key not in self.data:
            self.data[key] = []
        self.data[key].append(expr_key)
        self._save()

    def get_expr_keys(self, file_path: Path) -> list[str]:
        """Return expr_keys for a file from in-memory data.

        Args:
            file_path: Target file.

        Returns:
            List of expr_key strings (empty if none).
        """
        key = str(file_path.resolve())
        return self.data.get(key, [])

    def get_all_files(self) -> list[Path]:
        """Return all instrumented file paths.

        Returns:
            List of file paths.
        """
        return [Path(p) for p in self.data]

    def clear(self) -> None:
        """Delete registry file and clear in-memory data."""
        if self.registry_path.exists():
            self.registry_path.unlink()
        self.data = {}
