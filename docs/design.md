# Instrumentation Module – Design Specification

## Design Overview

The Instrumentation module modifies project source code by injecting runtime probes (`__logic_var` wrappers) around target expressions and provides restoration capabilities.

**Classes**: `InstrumentationManager` (internal), `InstrumentationRegistry`, `ASTInstrumenter` (internal), `ASTDeinstrumenter` (internal), `ASTStorageAccessor` (internal)

**Relationships**: 
- `InstrumentationManager` contains `InstrumentationRegistry`
- `InstrumentationManager` uses `ASTInstrumenter` for adding probes
- `InstrumentationManager` uses `ASTDeinstrumenter` for removing probes
- `ASTInstrumenter` uses `ASTStorageAccessor` for AST storage operations
- `ASTDeinstrumenter` uses `ASTStorageAccessor` for AST storage operations
- `instrument()` function uses `InstrumentationManager` internally
- `deinstrument()` function uses `InstrumentationManager` internally

**Abstract**: None

**Exceptions**: `InstrumentationError` extends `Exception`, `DeinstrumentationError` extends `InstrumentationError`

**Shared Components**: `LLMBoundCandidate` (from binding module with embedded `ASTCandidate`), `php_parser_py.AST`

**Resources**: `resources/beluga_runtime.php`
---

## Function Specifications

### Module: `beluga_core.binding._instrumentation`

**[instrument(candidates: List[LLMBoundCandidate], project_ast: AST) -> List[Path]]**
- **Responsibility**: Applies runtime probes to target code locations by wrapping expressions with `__logic_var` calls.
- **Behavior**: Creates `InstrumentationManager` internally, groups candidates by file, instruments each file using AST rewriting, registers modifications in registry, and returns list of modified file paths.
- **Input**: 
  - `candidates`: List of bindings to instrument
  - `project_ast`: Parsed project AST from static analysis
- **Output**: List of paths to modified files
- **Raises**: `InstrumentationError` on parse failure, write failure, or registry error

**Example Usage**:
```python
from beluga_core.binding import instrument
from php_parser_py import parse_file

project_ast = parse_file("project.php")
modified_files = instrument(bound_candidates, project_ast)
```

**[deinstrument(project_ast: AST, use_registry: bool = True) -> List[Path]]**
- **Responsibility**: Removes runtime probes to restore original code.
- **Behavior**: Creates `InstrumentationManager` internally. If `use_registry` is True, uses registry-based restoration (precise, requires valid registry). If False, uses scan-based restoration (fail-safe, scans all PHP files). Removes runtime helper and clears registry.
- **Input**: 
  - `project_ast`: Parsed project AST from static analysis
  - `use_registry`: If True, use registry mode; if False, use scan mode (default: True)
- **Output**: List of paths to restored files
- **Raises**: `DeinstrumentationError` on failure

**Example Usage**:
```python
from beluga_core.binding import deinstrument
from php_parser_py import parse_file

project_ast = parse_file("project.php")

# Use registry mode (default, precise)
restored_files = deinstrument(project_ast, use_registry=True)

# Use scan mode (fail-safe)
restored_files = deinstrument(project_ast, use_registry=False)
```

---

## Class Specifications

### InstrumentationManager Class (Internal)
- **Responsibility**: Internal implementation class for managing instrumentation lifecycle. Maintains state via `InstrumentationRegistry` and delegates operations to `ASTInstrumenter` and `ASTDeinstrumenter`.
- **Properties**: 
  - `project_ast: AST` - Parsed project AST from static analysis
  - `project_root: Path` - Root directory of the project (derived from `project_ast`)
  - `registry: InstrumentationRegistry` - State tracker instance
  - `_runtime_helper_name: str` - Name of runtime helper file ("beluga_runtime.php")
  - `_instrumenter: ASTInstrumenter` - AST instrumentation handler
  - `_deinstrumenter: ASTDeinstrumenter` - AST deinstrumentation handler
- **[__init__(project_ast: AST)]**
  - **Behavior**: Initializes manager with project AST, extracts project root from AST, creates/loads `InstrumentationRegistry` instance, and initializes `ASTInstrumenter` and `ASTDeinstrumenter`.
  - **Input**: `project_ast`: Parsed project AST from static analysis
  - **Output**: None
  - **Raises**: None
- **[instrument(candidates: List[LLMBoundCandidate]) -> List[Path]]**
  - **Behavior**: Returns empty list if candidates list is empty. Copies `resources/beluga_runtime.php` to project root if not present. Groups candidates by file path. For each file, instruments all candidates using `_instrumenter.instrument_file()`. Injects `require_once` statement for runtime helper. Returns list of paths to modified files.
  - **Input**: `candidates`: List of bindings to instrument
  - **Output**: List of paths to modified files
  - **Raises**: `InstrumentationError` on parse failure, write failure, or registry error
- **[deinstrument(use_registry: bool = True) -> List[Path]]**
  - **Behavior**: If `use_registry` is True, uses `self.registry` to identify probe locations and unwraps via `_deinstrument_registry()` method. If `use_registry` is False, scans all PHP files using `_deinstrument_scan()` method. Removes `beluga_runtime.php` and clears registry via `_cleanup()` method. Returns list of paths to restored files.
  - **Input**: `use_registry`: If True, use registry mode; if False, use scan mode
  - **Output**: List of paths to restored files
  - **Raises**: `DeinstrumentationError` on failure

**Example Usage**:
```python
from beluga_core.binding._instrumentation._manager import InstrumentationManager
from php_parser_py import parse_file

project_ast = parse_file("project.php")
manager = InstrumentationManager(project_ast)

# Instrument candidates
modified_files = manager.instrument(bound_candidates)

# Deinstrument (registry-based)
restored_files = manager.deinstrument(use_registry=True)

# Deinstrument (scan-based)
restored_files = manager.deinstrument(use_registry=False)
```

### InstrumentationRegistry Class
- **Responsibility**: Persists instrumentation state to `.beluga_registry.json` for precise restoration during deinstrumentation.
- **Properties**: 
  - `project_root: Path` - Absolute path to project root
  - `registry_path: Path` - Path to the registry file (`.beluga_registry.json`)
  - `data: Dict[str, List[InstrumentationEntry]]` - In-memory state (maps file paths to entries)
- **[__init__(project_root: Path)]**
  - **Behavior**: Initializes registry with project root, sets registry path, and loads existing registry from disk if present.
  - **Input**: `project_root`: Absolute path to project root
  - **Output**: None
  - **Raises**: None
- **[register(file_path: Path, entry: InstrumentationEntry) -> None]**
  - **Behavior**: Records an instrumentation point in memory and persists to disk atomically.
  - **Input**: 
    - `file_path`: Modified file path
    - `entry`: Metadata dict containing `id`, `var_name`, `start_byte`, `end_byte`
  - **Output**: None
  - **Raises**: `OSError` on write failure
- **[get_entries(file_path: Path) -> List[InstrumentationEntry]]**
  - **Behavior**: Retrieves entries for a specific file from in-memory data.
  - **Input**: `file_path`: Target file path
  - **Output**: List of entries for that file
  - **Raises**: None
- **[get_all_files() -> List[Path]]**
  - **Behavior**: Gets all instrumented file paths from registry.
  - **Input**: None
  - **Output**: List of file paths
  - **Raises**: None
- **[clear() -> None]**
  - **Behavior**: Deletes the registry file from disk and clears in-memory data.
  - **Input**: None
  - **Output**: None
  - **Raises**: None

**Example Usage**:
```python
from beluga_core.binding._instrumentation._registry import InstrumentationRegistry

registry = InstrumentationRegistry(project_root)
entry = {
    "id": "probe_1",
    "var_name": "total",
    "start_byte": 100,
    "end_byte": 150
}
registry.register(file_path, entry)
entries = registry.get_entries(file_path)
```

### ASTInstrumenter Class (Internal)
- **Responsibility**: Handles AST manipulation for adding instrumentation probes. Wraps target expressions with `__logic_var` function calls.
- **Properties**: 
  - `project_ast: AST` - Parsed project AST
  - `registry: InstrumentationRegistry` - Registry for tracking instrumentation
- **[__init__(project_ast: AST, registry: InstrumentationRegistry)]**
  - **Behavior**: Initializes instrumenter with project AST and registry.
  - **Input**: 
    - `project_ast`: Parsed project AST
    - `registry`: Registry for tracking instrumentation
  - **Output**: None
  - **Raises**: None
- **[instrument_file(file_path: Path, candidates: List[LLMBoundCandidate]) -> None]**
  - **Behavior**: Instruments a single file by building node-to-candidate mapping, processing and instrumenting nodes using AST storage operations, and regenerating file content using PrettyPrinter.
  - **Input**: 
    - `file_path`: Target file path
    - `candidates`: List of bound candidates for this file
  - **Output**: None
  - **Raises**: `InstrumentationError` on AST manipulation failure or file node not found

**Example Usage**:
```python
from beluga_core.binding._instrumentation._ast_operations import ASTInstrumenter
from beluga_core.binding._instrumentation._registry import InstrumentationRegistry

instrumenter = ASTInstrumenter(project_ast, registry)
instrumenter.instrument_file(file_path, candidates)
```

### ASTDeinstrumenter Class (Internal)
- **Responsibility**: Handles AST manipulation for removing instrumentation probes. Unwraps `__logic_var` calls to restore original expressions.
- **Properties**: None
- **[__init__()]**
  - **Behavior**: Creates deinstrumenter instance.
  - **Input**: None
  - **Output**: None
  - **Raises**: None
- **[unwrap_probe_ast(file_path: Path, entry: InstrumentationEntry, ast, exclude_node_ids: Optional[set] = None) -> bool]**
  - **Behavior**: Unwraps a single `__logic_var` call in AST by replacing it with original expression. Uses AST rewrite: finds the call node, extracts second argument, replaces call with expression. Returns True if call was found and replaced, False otherwise.
  - **Input**: 
    - `file_path`: Target file (for error messages)
    - `entry`: Registry entry with var_name
    - `ast`: Parsed AST (will be modified in place)
    - `exclude_node_ids`: Set of node IDs to exclude from matching
  - **Output**: True if call was found and replaced, False otherwise
  - **Raises**: `DeinstrumentationError` if structure invalid
- **[scan_and_unwrap(project_root: Path) -> List[Path]]**
  - **Behavior**: Scans all PHP files and unwraps `__logic_var` calls using AST transformation. Parses each file to AST, finds all `__logic_var` function calls, replaces them with their second argument (original expression), and regenerates the file.
  - **Input**: `project_root`: Root directory
  - **Output**: List of modified file paths
  - **Raises**: `DeinstrumentationError` on parse or write errors

**Example Usage**:
```python
from beluga_core.binding._instrumentation._ast_operations import ASTDeinstrumenter

deinstrumenter = ASTDeinstrumenter()
result = deinstrumenter.unwrap_probe_ast(file_path, entry, ast)
modified_files = deinstrumenter.scan_and_unwrap(project_root)
```

### ASTStorageAccessor Class (Internal)
- **Responsibility**: Provides static utility methods for AST storage operations. Wraps direct `_storage` access to centralize protected member access.
- **Properties**: None (static methods only)
- **[add_node(ast, node_id: str) -> None]**
  - **Behavior**: Adds a node to AST storage.
  - **Input**: 
    - `ast`: AST instance
    - `node_id`: Node identifier
  - **Output**: None
  - **Raises**: None
- **[set_node_props(ast, node_id: str, props: dict) -> None]**
  - **Behavior**: Sets properties on a node in AST storage.
  - **Input**: 
    - `ast`: AST instance
    - `node_id`: Node identifier
    - `props`: Properties dictionary
  - **Output**: None
  - **Raises**: None
- **[get_node_props(ast, node_id: str) -> dict]**
  - **Behavior**: Gets properties from a node in AST storage.
  - **Input**: 
    - `ast`: AST instance
    - `node_id`: Node identifier
  - **Output**: Properties dictionary
  - **Raises**: None
- **[add_edge(ast, edge: tuple) -> None]**
  - **Behavior**: Adds an edge to AST storage.
  - **Input**: 
    - `ast`: AST instance
    - `edge`: Edge tuple (from_nid, to_nid, type)
  - **Output**: None
  - **Raises**: None
- **[set_edge_props(ast, edge: tuple, props: dict) -> None]**
  - **Behavior**: Sets properties on an edge in AST storage.
  - **Input**: 
    - `ast`: AST instance
    - `edge`: Edge tuple (from_nid, to_nid, type)
    - `props`: Properties dictionary
  - **Output**: None
  - **Raises**: None
- **[get_edge_props(ast, edge: tuple) -> dict]**
  - **Behavior**: Gets properties from an edge in AST storage.
  - **Input**: 
    - `ast`: AST instance
    - `edge`: Edge tuple (from_nid, to_nid, type)
  - **Output**: Properties dictionary
  - **Raises**: None
- **[remove_edge(ast, edge: tuple) -> None]**
  - **Behavior**: Removes an edge from AST storage.
  - **Input**: 
    - `ast`: AST instance
    - `edge`: Edge tuple (from_nid, to_nid, type)
  - **Output**: None
  - **Raises**: None

**Example Usage**:
```python
from beluga_core.binding._instrumentation._ast_operations import ASTStorageAccessor

ASTStorageAccessor.add_node(ast, "node_1")
ASTStorageAccessor.set_node_props(ast, "node_1", {"nodeType": "Name"})
props = ASTStorageAccessor.get_node_props(ast, "node_1")
```

---

## Exception Classes

**InstrumentationError**: Raised when an error occurs during the instrumentation process (e.g., parse error, write failure, registry error, runtime helper not found). Raised by `instrument()` function and `InstrumentationManager.instrument()` method.

**DeinstrumentationError**: Extends `InstrumentationError`. Raised when code restoration fails (e.g., registry corrupted, file modified externally, AST parse error). Raised by `deinstrument()` function and `InstrumentationManager.deinstrument()` method.

---

## Validation Rules

### Interface Consistency Validation
- **Public API**: `instrument()` and `deinstrument()` are the primary public functions. `InstrumentationManager` is an internal implementation class.
- **State Encapsulation**: Registry state is fully encapsulated within `InstrumentationManager`.
- **AST Operations**: AST manipulation is delegated to `ASTInstrumenter` and `ASTDeinstrumenter` classes.

### Safety Validation
- **Syntax Check**: All modified files MUST pass `php-parser-py` parse checks before writing.
- **Atomic Operations**: Registry file updates should be atomic to prevent corruption.
- **Fail-Safe**: If registry is missing or corrupted, `deinstrument()` can use scan mode (`use_registry=False`) as fallback.

### Runtime Helper Validation
- **Presence Check**: Runtime helper file is copied to project root only if not already present.
- **Require Injection**: `require_once` statement for runtime helper is injected into instrumented files.

### Deinstrumentation Modes Validation
- **Registry Mode** (`use_registry=True`): Precise restoration using registry data. Requires valid registry file. Faster and more accurate.
- **Scan Mode** (`use_registry=False`): Fail-safe restoration by scanning all PHP files. Works even if registry is missing or corrupted. Slower but more robust.
