"""Instrumentation orchestration logic.

Provides InstrumentationManager for lifecycle management and public API
functions instrument() and deinstrument().
"""

from __future__ import annotations

import importlib.resources
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from php_parser_py import AST, Node, Parser, PrettyPrinter

from ._exceptions import DeinstrumentationError, InstrumentationError
from ._operations import _PROBE_FUNC_PREFIX, ASTDeinstrumenter, ASTInstrumenter
from ._registry import InstrumentationRegistry
from ._strategies import ProbeStrategy, StandardProbeStrategy

logger = logging.getLogger(__name__)

_RUNTIME_HELPER_NAME = "porifera_runtime.php"


class InstrumentationManager:
    """Orchestrates instrumentation lifecycle: resolves file membership from AST,
    delegates wrapping to ASTInstrumenter, manages file regeneration, runtime helper
    injection, and registry.

    Attributes:
        project_ast: Parsed project AST.
        registry: State tracker for instrumented files.
    """

    def __init__(
        self,
        project_ast: AST,
        strategy: ProbeStrategy | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self.project_ast = project_ast
        self._project_root = self._resolve_project_root(project_ast)
        self.registry = InstrumentationRegistry(
            self._project_root / ".porifera_registry.json",
        )

        self._probe_func_name = f"{_PROBE_FUNC_PREFIX}{uuid.uuid4().hex[:8]}"
        self._output_dir = output_dir
        self._timestamp = (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        if strategy is None:
            strategy = StandardProbeStrategy()

        self._instrumenter = ASTInstrumenter(
            self.project_ast,
            strategy,
            self._probe_func_name,
        )
        self._deinstrumenter = ASTDeinstrumenter()

    @staticmethod
    def _resolve_project_root(project_ast: AST) -> Path:
        """Resolve project root from AST; tries project node, falls back to first file node."""
        try:
            project_node = project_ast.project_node()
            path_val = project_node.get_property("absolutePath")
            if path_val is not None and str(path_val).strip():
                return Path(str(path_val)).resolve()
        except KeyError:
            pass

        for file_node in project_ast.file_nodes():
            file_path_val = file_node.get_property("absolutePath")
            if file_path_val is not None and str(file_path_val).strip():
                p = Path(str(file_path_val)).resolve()
                return p.parent if p.is_file() else p

        raise InstrumentationError(
            "Could not resolve project root: no absolutePath in project or file nodes",
        )

    def instrument(self, targets: dict[str, str]) -> list[Path]:
        """Apply runtime probes to target code locations.

        Args:
            targets: Maps node_id -> expr_key.

        Returns:
            List of modified file paths.

        Raises:
            InstrumentationError: On failure.
        """
        if not targets:
            return []

        self._ensure_runtime_helper()
        by_file = self._group_targets_by_file(targets)
        modified_files: list[Path] = []

        for file_path, file_targets in by_file.items():
            file_modified = False
            for node_id, expr_key in file_targets.items():
                if self._instrumenter.instrument_node(node_id, expr_key):
                    self.registry.register(file_path, expr_key)
                    file_modified = True

            if file_modified:
                self._regenerate_file(file_path)
                self._inject_require(file_path)
                modified_files.append(file_path)

        return modified_files

    def deinstrument(self, use_registry: bool = True) -> list[Path]:
        """Remove runtime probes to restore original code.

        Args:
            use_registry: If True, use registry mode; if False, use scan mode.

        Returns:
            List of restored file paths.

        Raises:
            DeinstrumentationError: On failure.
        """
        try:
            if use_registry:
                modified_files = self._deinstrument_registry()
            else:
                modified_files = self._deinstrument_scan()
        finally:
            self._cleanup()
        return modified_files

    def _group_targets_by_file(
        self, targets: dict[str, str]
    ) -> dict[Path, dict[str, str]]:
        """Group targets by file, resolving file membership from AST."""
        by_file: dict[Path, dict[str, str]] = {}
        for node_id, expr_key in targets.items():
            file_path = self._resolve_file_for_node(node_id)
            by_file.setdefault(file_path, {})[node_id] = expr_key
        return by_file

    def _resolve_file_for_node(self, node_id: str) -> Path:
        """Resolve which file a node belongs to via ast.get_file_node()."""
        file_node = self.project_ast.get_file_node(node_id)
        abs_path = file_node.get_property("absolutePath")
        if abs_path:
            return Path(str(abs_path)).resolve()

        raise InstrumentationError(
            f"Could not resolve file for node {node_id}: File node has no absolutePath",
        )

    def _regenerate_file(self, file_path: Path) -> None:
        """Regenerate file content using PrettyPrinter."""
        file_node = self._find_file_node(file_path)
        if file_node is None:
            raise InstrumentationError(f"No file node for {file_path} in AST")

        relative_path = file_node.get_property("relativePath")
        if relative_path is None:
            raise InstrumentationError(
                f"File node for {file_path} has no relativePath property",
            )

        new_content = PrettyPrinter().print_file(
            self.project_ast,
            str(relative_path),
        )
        file_path.write_text(new_content, encoding="utf-8")

    def _find_file_node(self, file_path: Path) -> Node | None:
        """Find the file node in AST for the given file path."""
        abs_path_str = str(file_path.resolve())
        for f in self.project_ast.file_nodes():
            node_path = f.get_property("absolutePath")
            if node_path and str(node_path) == abs_path_str:
                return f
        return None

    def _ensure_runtime_helper(self) -> None:
        """Copy runtime helper to project root with placeholders substituted.

        Always overwrites any existing helper to guarantee the probe function
        name matches the current InstrumentationManager instance.
        """
        dest = self._project_root / _RUNTIME_HELPER_NAME

        template_ref = importlib.resources.files(
            "porifera.resources",
        ).joinpath(_RUNTIME_HELPER_NAME)
        template_content = template_ref.read_text(encoding="utf-8")

        if self._output_dir is not None:
            php_output_dir = f"'{self._output_dir.resolve()}'"
        else:
            php_output_dir = "__DIR__"

        content = (
            template_content.replace("{{PROBE_FUNC_NAME}}", self._probe_func_name)
            .replace("{{OUTPUT_DIR}}", php_output_dir)
            .replace("{{TIMESTAMP}}", self._timestamp)
        )
        dest.write_text(content, encoding="utf-8")

    def _inject_require(self, file_path: Path) -> None:
        """Inject require_once for runtime helper after <?php tag."""
        content = file_path.read_text(encoding="utf-8")

        # Compute relative path from the PHP file's directory to the project root
        # so subdirectory files can find the runtime helper.
        file_dir = file_path.parent
        rel_path = os.path.relpath(self._project_root, file_dir)
        if rel_path == ".":
            require_path = f"__DIR__ . '/{_RUNTIME_HELPER_NAME}'"
        else:
            require_path = f"__DIR__ . '/{rel_path}/{_RUNTIME_HELPER_NAME}'"
        require_line = f"require_once {require_path};"

        if _RUNTIME_HELPER_NAME in content:
            return

        if "<?php" in content:
            content = content.replace(
                "<?php",
                f"<?php\n{require_line}\n",
                1,
            )
            file_path.write_text(content, encoding="utf-8")

    def _remove_require(self, file_path: Path) -> bool:
        """Remove require_once for runtime helper from file."""
        if not file_path.exists():
            return False
        content = file_path.read_text(encoding="utf-8")
        if _RUNTIME_HELPER_NAME not in content:
            return False

        lines = content.splitlines(keepends=True)
        new_lines = [
            line
            for line in lines
            if not ("require_once" in line and _RUNTIME_HELPER_NAME in line)
        ]
        new_content = "".join(new_lines)
        if new_content == content:
            return False
        file_path.write_text(new_content, encoding="utf-8")
        return True

    def _deinstrument_registry(self) -> list[Path]:
        """Deinstrument using registry data for precise restoration."""
        modified_files: list[Path] = []

        for file_path in self.registry.get_all_files():
            expr_keys = self.registry.get_expr_keys(file_path)
            unwrapped_count = 0
            if expr_keys:
                unwrapped_count = self._unwrap_file_entries(file_path, expr_keys)

            require_removed = self._remove_require(file_path)
            if unwrapped_count > 0 or require_removed:
                modified_files.append(file_path)

        return modified_files

    def _unwrap_file_entries(self, file_path: Path, expr_keys: list[str]) -> int:
        """Unwrap all probe function calls in a file using parsed AST."""
        ast = Parser().parse_file(str(file_path))

        unwrapped_count = 0
        processed_node_ids: set[str] = set()
        for expr_key in expr_keys:
            if self._deinstrumenter.unwrap_probe_ast(
                file_path,
                expr_key,
                ast,
                processed_node_ids,
            ):
                unwrapped_count += 1

        if unwrapped_count > 0:
            result = PrettyPrinter().print(ast)
            if not result:
                raise DeinstrumentationError(
                    f"PrettyPrinter produced no output for {file_path}",
                )
            file_path.write_text(next(iter(result.values())), encoding="utf-8")

        return unwrapped_count

    def _deinstrument_scan(self) -> list[Path]:
        """Deinstrument using scan mode — scans all PHP files."""
        modified_files = self._deinstrumenter.scan_and_unwrap(self._project_root)
        for php_file in self._project_root.rglob("*.php"):
            if self._remove_require(php_file) and php_file not in modified_files:
                modified_files.append(php_file)
        return modified_files

    def _cleanup(self) -> None:
        """Remove runtime helper and registry."""
        runtime_path = self._project_root / _RUNTIME_HELPER_NAME
        if runtime_path.exists():
            runtime_path.unlink()
        self.registry.clear()


def instrument(
    targets: dict[str, str],
    project_ast: AST,
    strategy: ProbeStrategy | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    """Public API for applying runtime probes to target expressions.

    Creates InstrumentationManager internally, delegates to manager.instrument().

    Args:
        targets: Maps node_id -> expr_key.
        project_ast: Parsed project AST.
        strategy: Wrapping strategy (default: StandardProbeStrategy).
        output_dir: Directory for probe output file. Defaults to project root.

    Returns:
        List of modified file paths.

    Raises:
        InstrumentationError: On failure.
    """
    manager = InstrumentationManager(project_ast, strategy, output_dir)
    return manager.instrument(targets)


def deinstrument(
    project_ast: AST,
    use_registry: bool = True,
) -> list[Path]:
    """Public API for removing runtime probes.

    Creates InstrumentationManager internally, delegates to manager.deinstrument().

    Args:
        project_ast: Parsed project AST.
        use_registry: Registry mode (True) or scan mode (False).

    Returns:
        List of restored file paths.

    Raises:
        DeinstrumentationError: On failure.
    """
    manager = InstrumentationManager(project_ast)
    return manager.deinstrument(use_registry)
