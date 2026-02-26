# Instrumentation Module – Implementation Notes

## APIs

### AST Traversal & Querying

**[php-parser-py]** `AST.project_node() -> Node` — returns project root node; raises `KeyError` if root missing.

**[php-parser-py]** `AST.files() -> list[Node]` — list of all File nodes; each has `get_property("absolutePath")` and `get_property("relativePath")`.

**[php-parser-py]** `AST.get_file(node_id) -> Node` — get the File node containing a specific node.

**[php-parser-py]** `AST.node(id) -> Node` — get node by ID; raises `KeyError` if not found.

**[php-parser-py]** `AST.nodes(predicate) -> Iterable[Node]` — generator with optional lambda filter.

**[php-parser-py]** `AST.edges(predicate) -> Iterable[Edge]` — generator with optional lambda filter.

**[php-parser-py]** `AST.first_node(predicate)` — find first node matching predicate.

**[php-parser-py]** `AST.succ(node) -> list[Node]` — child nodes.

**[php-parser-py]** `AST.prev(node) -> list[Node]` — parent nodes.

**[php-parser-py]** `AST.descendants(node) -> Iterable[Node]` — all descendants (BFS).

**[php-parser-py]** `AST.ancestors(node) -> Iterable[Node]` — all ancestors (BFS).

**[php-parser-py]** `AST.edge(from_id, to_id, edge_type) -> Edge` — direct edge lookup by endpoint IDs and type.

### Node API

**[php-parser-py]** `Node.node_type -> str` — e.g. `"Stmt_For"`, `"Expr_FuncCall"`.

**[php-parser-py]** `Node.id -> str` — unique node identifier.

**[php-parser-py]** `Node.start_line -> int`, `Node.end_line -> int` — typed convenience properties; prefer over `get_property("startLine")`.

**[php-parser-py]** `Node.get_property("propName") -> Any` — generic property lookup; works for JSON properties including "absolutePath", "relativePath", "nodeType", "parts", "value".

**[php-parser-py]** `Node.set_property(key, value)` — set a single property on the node.

**[php-parser-py]** `Node.set_properties(props: dict)` — set multiple properties on the node at once.

### Edge API

**[php-parser-py]** `Edge.from_nid -> str`, `Edge.to_nid -> str`, `Edge.type -> str` — edge endpoints and type.

**[php-parser-py]** `Edge.get_property("field") -> Any`, `Edge.get("field") -> Any` — edge metadata; PARENT_OF edges have "field" (str) and optionally "index" (int) properties. These are NOT direct attributes on the Edge class.

### Graph Mutation (via `Modifier`)

Structural AST mutations use the `Modifier` class (php-parser-py >=1.2.2). The AST query interface remains read-only; all mutations go through `Modifier`.

- `Modifier(ast)` — constructor; wraps an AST for mutation
- `modifier.add_node(node_id, node_type, **props) -> Node` — add a new node with type and properties; returns the created Node
- `modifier.add_edge(from_id, to_id, field=..., index=...) -> None` — add a PARENT_OF edge with field and optional index
- `modifier.remove_edge(from_id, to_id) -> None` — remove a PARENT_OF edge
- `modifier.remove_node(node_id) -> None` — remove a node and all connected edges
- `modifier.ast -> AST` — access the underlying AST after modifications
- `node.set_property(key, value)` / `node.set_properties(dict)` — modify node properties directly via Node API (not through Modifier)

### Code Generation & Parsing

**[php-parser-py]** `PrettyPrinter().print(ast) -> dict[str, str]` — returns dict mapping file paths to PHP code; NOT a string. Use `print_file()` for single-file string output.

**[php-parser-py]** `PrettyPrinter().print_file(ast, relative_path) -> str` — returns PHP code string for one file.

**[php-parser-py]** `Parser().parse_file(path) -> AST` — parse a single PHP file into an AST.

## Libraries

- **php-parser-py>=1.2.2** — Python wrapper for nikic/PHP-Parser; AST graph with project/file/statement node hierarchy; provides traversal, querying, node property management, and structural mutation via `Modifier` class.

## Developer Instructions

- Prefer php-parser-py traversal methods over manual edge filtering:
  - `ast.prev(node)` for parent lookup instead of `ast.edges(lambda e: e.to_nid == node.id and ...)`
  - `ast.succ(node)` for children instead of `ast.edges(lambda e: e.from_nid == node.id and ...)`
  - `ast.edge(from_id, to_id, "PARENT_OF")` for direct edge lookup
  - `ast.get_file(node_id)` for resolving file membership instead of walking ancestors manually
- Use `node.get_property("key")` and `edge.get("key")` for property reads.
- Use `node.set_property(key, value)` or `node.set_properties(dict)` for node property writes.
- Use `Modifier(ast)` for structural mutations (add_node, add_edge, remove_edge, remove_node).
- Edge properties "field" and "index" are accessed via `edge.get_property("field")` or `edge.get("field")`; they are NOT direct attributes on the Edge class.
- `PrettyPrinter().print(ast)` always returns `dict[str, str]`; for single-file writes, extract the value with `next(iter(result.values()))` or use `print_file()`.
- Node line numbers: prefer `node.start_line` / `node.end_line` (typed int properties) over `node.get_property("startLine")`.
- `AST.project_node()` is always a method; raises `KeyError` if root missing. No need for `getattr/callable` guards.
- Reference: [cpg2py traversal API](https://github.com/jhu-seclab-beluga/php-parser-py/blob/main/docs/libs/cpg2py_traversal.md)

## Design-Specific

### PHP AST Node Types for Loops and Control Flow

| Node Type | Fields | Notes |
|-----------|--------|-------|
| `Stmt_For` | `init[]`, `cond[]`, `loop[]`, `stmts[]` | `init`/`cond`/`loop` are arrays of Expr nodes |
| `Stmt_While` | `cond`, `stmts[]` | `cond` is a single Expr node |
| `Stmt_Do` | `cond`, `stmts[]` | condition evaluated after body |
| `Stmt_Foreach` | `expr`, `keyVar`, `valueVar`, `byRef`, `stmts[]` | `keyVar`/`valueVar` are lvalues |
| `Stmt_Switch` | `cond`, `cases[]` | each `Stmt_Case` has optional `cond` + `stmts[]` |
| `Stmt_If` | `cond`, `stmts[]`, `elseifs[]`, `else` | `Stmt_ElseIf` has `cond` + `stmts[]` |

### Unsafe Wrap Contexts

`_UNSAFE_WRAP_CONTEXTS` is a module-level `frozenset[tuple[str, str]]` in `_strategies.py`, mapping `(parent_node_type, edge_field)` pairs. Module-level `_is_safe_to_wrap(ast, node)` checks against this set; used by both `StandardProbeStrategy` and `ElevatingProbeStrategy`.

**Category A — Lvalue contexts** (wrapping converts lvalue to rvalue -> PHP error):

| Parent Node Type | Edge Field | PHP Example |
|-----------------|------------|-------------|
| `Expr_Assign` | `var` | `$x = 1` — `$x` is assignment target |
| `Expr_AssignRef` | `var` | `$x =& $y` — `$x` is reference target |
| `Expr_AssignOp_Plus` | `var` | `$x += 1` |
| `Expr_AssignOp_Minus` | `var` | `$x -= 1` |
| `Expr_AssignOp_Mul` | `var` | `$x *= 2` |
| `Expr_AssignOp_Div` | `var` | `$x /= 2` |
| `Expr_AssignOp_Mod` | `var` | `$x %= 2` |
| `Expr_AssignOp_Concat` | `var` | `$x .= "str"` |
| `Expr_AssignOp_BitwiseAnd` | `var` | `$x &= 0xFF` |
| `Expr_AssignOp_BitwiseOr` | `var` | `$x \|= 0x01` |
| `Expr_AssignOp_BitwiseXor` | `var` | `$x ^= 0xFF` |
| `Expr_AssignOp_ShiftLeft` | `var` | `$x <<= 2` |
| `Expr_AssignOp_ShiftRight` | `var` | `$x >>= 2` |
| `Expr_AssignOp_Pow` | `var` | `$x **= 2` |
| `Expr_AssignOp_Coalesce` | `var` | `$x ??= "default"` |
| `Expr_PreInc` | `var` | `++$x` |
| `Expr_PostInc` | `var` | `$x++` |
| `Expr_PreDec` | `var` | `--$x` |
| `Expr_PostDec` | `var` | `$x--` |
| `Stmt_Foreach` | `keyVar` | `foreach($arr as $k => $v)` — `$k` |
| `Stmt_Foreach` | `valueVar` | `foreach($arr as $v)` — `$v` |
| `Stmt_Unset` | `vars` | `unset($x)` |

**Category C — Reference contexts**:

| Parent Node Type | Edge Field | Reason |
|-----------------|------------|--------|
| `Expr_AssignRef` | `expr` | Right side of `$x =& $y` must be a variable; wrapping breaks reference binding |

**Safe contexts** (rvalue, wrapping is correct):
- `Expr_Assign.expr` — right side of assignment
- `Stmt_For.init` — init expressions; for-loop discards return values; safe for wrapping expressions (lvalues inside are handled by elevation)
- `Stmt_For.cond` — loop condition (rvalue); note: probe executes every iteration
- `Stmt_For.loop` — loop update expressions; for-loop discards return values; safe for wrapping expressions (lvalues inside are handled by elevation)
- `Stmt_While.cond` — while condition (rvalue); probe executes every iteration
- `Stmt_Do.cond` — do-while condition (rvalue); probe executes every iteration
- `Stmt_If.cond`, `Stmt_ElseIf.cond`, `Stmt_Switch.cond` — conditions (rvalue)
- `Arg.value` — function argument (non-byRef)
- `Stmt_Return.expr` — return value
- `Stmt_Echo.exprs` — echo arguments

### Known Limitations

- **By-ref function arguments**: detecting whether a callee parameter is declared `&$param` requires resolving the function signature (static analysis); not detectable at AST manipulation layer. If a target expression is passed by reference, wrapping silently breaks pass-by-reference semantics.
- **`Expr_List` destructuring**: `list($a, $b) = $arr` — the variables inside `Expr_List` are lvalues, but they appear as `Expr_ArrayItem.value` children. Distinguishing destructuring from normal array values requires multi-level ancestor check. Current approach relies on upstream filtering to not propose destructuring targets.
- **Probe execution frequency**: wrapping expressions in loop conditions (`Stmt_For.cond`, `Stmt_While.cond`, `Stmt_Do.cond`) causes the probe to execute every iteration. This is a performance concern, not a correctness concern.

### Probe Naming and Identification

- `_PROBE_FUNC_PREFIX = "__lemur_probe_"` — module constant in `_instrumenter.py`.
- Probe function names are auto-generated: `f"{_PROBE_FUNC_PREFIX}{uuid.uuid4().hex[:8]}"` (e.g. `__lemur_probe_a1b2c3d4`).
- Name is generated once per `InstrumentationManager` session; passed to `ASTInstrumenter`. Strategies never see it.
- Deinstrumentation matches by prefix (`parts[0].startswith(_PROBE_FUNC_PREFIX)`) — no need to persist or know the exact name.
- Fast-path text filter in scan mode: `_PROBE_FUNC_PREFIX not in content`.

### ProbeStrategy / StandardProbeStrategy / ElevatingProbeStrategy

- `ProbeStrategy` is the ABC; pure target selection — no AST mutation, no probe naming.
- `select_wrap_target(ast, node, wrapped_node_ids) -> Optional[Node]` — returns the node to wrap, or None.
- `StandardProbeStrategy`: no constructor params. `select_wrap_target()`: `_is_safe_to_wrap()` → True → return node; False → return None.
- `ElevatingProbeStrategy`: no constructor params. `select_wrap_target()`: safe → return node; unsafe → walks parent chain via `ast.prev()` until non-`Expr_*` boundary → finds first `Expr_*` ancestor in safe context → return ancestor; no ancestor → return None.

### ASTInstrumenter

- Owns `_probe_func_name` (from Manager) and `_wrap_node()` logic. Uses `ProbeStrategy` only for target selection.
- `instrument_node()` calls `_strategy.select_wrap_target()` → if None, logs warning and returns False → otherwise calls `_wrap_node()`, adds to `_wrapped_nodes`, returns True.
- `_wrap_node()` creates probe call AST nodes via `Modifier.add_node()` with properties cloned from the target node.
- `_wrap_node()` parent edge replacement: find parent via `ast.prev(node)`, get edge via `ast.edge()`, save props via `edge.get()`, remove it, re-parent target under new arg node, attach func_call node to original parent with original edge props.
- `_is_safe_to_wrap` is a module-level function; finds parent via `ast.prev(node)`, gets edge field via `edge.get("field")`, checks `(parent_type, edge_field)` against `_UNSAFE_WRAP_CONTEXTS`.
- `_UNSAFE_WRAP_CONTEXTS` contains Category A (lvalue) and Category C (reference) entries only. `Stmt_For.init` and `Stmt_For.loop` are NOT in the unsafe set.
- Tracks `_wrapped_nodes: set` to prevent double-wrapping when multiple targets elevate to the same ancestor.
- File regeneration is handled by `InstrumentationManager`, not by `ASTInstrumenter`.

### Ancestor Elevation (ElevatingProbeStrategy)

- Elevation walks up via `ast.prev(current)` to get parent nodes; checks each ancestor with `_is_safe_to_wrap()`.
- Ancestor must be an expression node (`node_type.startswith("Expr_")`); statement nodes are not wrappable.
- For-loop example: `for($i = 1; $i < 10; $i++)`:
  - `$i` in init (`Expr_Assign.var`): elevates to `Expr_Assign` → in `Stmt_For.init` (safe) → `for(__probe("i", $i = 1); ...)`
  - `$i` in cond: rvalue, standard wrap → `for(...; __probe("i", $i) < 10; ...)`
  - `$i` in loop (`Expr_PostInc.var`): elevates to `Expr_PostInc` → in `Stmt_For.loop` (safe) → `for(...; ...; __probe("i", $i++))`
- Un-instrumentable: `Stmt_Foreach.keyVar`, `Stmt_Foreach.valueVar`, `Stmt_Unset.vars` — parent is a statement, no `Expr_*` ancestor.
- PHP syntax validity verified (PHP 8.5): `for(__probe("i", $i = 1); ...; __probe("i", $i++))` is valid PHP; assignment/increment as function arguments preserves side effects; for-loop discards return values.

### ASTDeinstrumenter

- No constructor params; identifies probes by `_PROBE_FUNC_PREFIX` prefix matching.
- `_is_probe_call` checks `parts[0].startswith(_PROBE_FUNC_PREFIX)` instead of exact name match.
- Probe call structure: `Expr_FuncCall` -> name (Name with `parts=[__lemur_probe_XXXXXXXX]`), args[0] (Arg -> Scalar_String with expr_key), args[1] (Arg -> original expression).
- `_process_php_file_for_unwrap` text search uses `_PROBE_FUNC_PREFIX` for the fast-path check.
- `scan_and_unwrap` parses each file independently with `Parser().parse_file()`; `PrettyPrinter().print(ast)` result is a single-entry dict for single-file ASTs.
- `unwrap_probe_ast` takes `expr_key: str` directly (not a TypedDict entry); modifies AST in place.

### InstrumentationManager

- `__init__` accepts optional `strategy: ProbeStrategy`; defaults to `StandardProbeStrategy()`. Auto-generates `probe_func_name` with `_PROBE_FUNC_PREFIX` + 8-char hex. Creates `ASTInstrumenter(project_ast, strategy, probe_func_name)` and `ASTDeinstrumenter()`.
- `instrument(targets: Dict[str, str])` accepts `node_id → expr_key` mapping; resolves file membership via AST ancestor traversal; groups by file; delegates wrapping per-node to `ASTInstrumenter.instrument_node()`.
- Registry stores `List[str]` (expr_keys) per file — no TypedDict, no unused fields.
- File regeneration uses `PrettyPrinter().print_file(ast, relative_path)` which returns a string; handled by Manager after all nodes in a file are instrumented.
- `_resolve_project_root`: tries `project_ast.project_node()` first, falls back to first file node's `absolutePath`. Result stored as private `_project_root`.
- `_RUNTIME_HELPER_NAME = "lemur_runtime.php"` — module constant in `_manager.py`; not configurable.
- `_inject_require` adds `require_once __DIR__ . '/lemur_runtime.php';` via text replacement after `<?php` tag.
- `_remove_require` removes the `require_once` line during deinstrumentation; called after AST-based probe unwrap since PrettyPrinter re-emits the `require_once` from the parsed AST.
- Registry mode: precise restoration using `.lemur_registry.json`. Scan mode: fail-safe by scanning all `.php` files.
