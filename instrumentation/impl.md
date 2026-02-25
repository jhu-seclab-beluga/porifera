# Instrumentation Module – Implementation Notes

## APIs

**[php-parser-py]** `AST.storage -> Storage` — public property from cpg2py `AbcGraphQuerier`; provides `add_node()`, `set_node_props()`, `get_node_props()`, `add_edge()`, `set_edge_props()`, `get_edge_props()`, `remove_edge()` for direct graph mutation.

**[php-parser-py]** `AST.project_node() -> Node` — returns project root node; raises `KeyError` if root missing.

**[php-parser-py]** `AST.file_nodes() -> list[Node]` — sorted file nodes; each has `get_property("absolutePath")` and `get_property("relativePath")`.

**[php-parser-py]** `AST.nodes(predicate) -> Iterable[Node]` — generator with optional lambda filter.

**[php-parser-py]** `AST.edges(predicate) -> Iterable[Edge]` — generator with optional lambda filter.

**[php-parser-py]** `AST.node(id) -> Node` — get node by ID; raises `KeyError` if not found.

**[php-parser-py]** `Node.start_line -> int`, `Node.end_line -> int` — typed convenience properties; prefer over `get_property("startLine")`.

**[php-parser-py]** `Node.get_property("propName") -> Any` — generic property lookup; works for JSON properties including "absolutePath", "relativePath", "nodeType".

**[php-parser-py]** `Edge.from_nid -> str`, `Edge.to_nid -> str`, `Edge.type -> str` — edge endpoints and type.

**[php-parser-py]** `Edge.get_property("field") -> Any`, `Edge.get_property("index") -> Any` — edge metadata for PARENT_OF edges; "field" and "index" are storage properties, not direct attributes.

**[php-parser-py]** `PrettyPrinter().print(ast) -> dict[str, str]` — returns dict mapping file paths to PHP code; NOT a string. Use `print_file()` for single-file string output.

**[php-parser-py]** `PrettyPrinter().print_file(ast, relative_path) -> str` — returns PHP code string for one file.

**[php-parser-py]** `Parser().parse_file(path) -> AST` — parse a single PHP file into an AST.

## Libraries

- **php-parser-py** — Python wrapper for PHP-Parser; AST graph with project/file/statement node hierarchy; uses cpg2py Storage for graph operations.
- **cpg2py** — graph framework providing `Storage`, `AbcGraphQuerier`, `AbcNodeQuerier`, `AbcEdgeQuerier` base classes.

## Developer Instructions

- `ast.storage` is the correct accessor for cpg2py Storage (public property from `AbcGraphQuerier`); do not use `ast._storage`.
- Edge properties "field" and "index" are accessed via `edge.get_property("field")`, `edge.get("field")`, or `edge["field"]`; they are NOT direct attributes on the Edge class.
- `PrettyPrinter().print(ast)` always returns `dict[str, str]`; for single-file writes, extract the value with `next(iter(result.values()))` or use `print_file()`.
- Node line numbers: prefer `node.start_line` / `node.end_line` (typed int properties) over `node.get_property("startLine")`.
- `AST.project_node()` is always a method; raises `KeyError` if root missing. No need for `getattr/callable` guards.
- Query Context7 `/jhu-seclab-beluga/php-parser-py` for node structures; `/samhsu-dev/cpg2py` for graph traversal patterns.

## Design-Specific

### ASTStorageAccessor

- Wraps `ast.storage` (cpg2py public property) to centralize graph mutation calls.
- All methods delegate to `Storage.add_node()`, `Storage.set_node_props()`, etc.
- Edge tuple format: `(from_nid, to_nid, edge_type)`.

### ASTInstrumenter

- New probe nodes are created with "startLine"/"endLine" properties cloned from the target node, so PrettyPrinter places them on the correct lines.
- Parent edge replacement: find incoming PARENT_OF edge of target node, save its props, remove it, re-parent target under new arg node, attach func_call node to original parent with original edge props.
- File regeneration uses `PrettyPrinter().print_file(ast, relative_path)` which returns a string.

### ASTDeinstrumenter

- `scan_and_unwrap` parses each file independently with `Parser().parse_file()`; `PrettyPrinter().print(ast)` result is a single-entry dict for single-file ASTs.
- `unwrap_probe_ast` modifies AST in place; caller is responsible for writing code back to file.
- `__logic_var` call structure: `Expr_FuncCall` → name (Name with parts=["__logic_var"]), args[0] (Arg → Scalar_String with var_name), args[1] (Arg → original expression).

### InstrumentationManager

- `_resolve_project_root`: tries `project_ast.project_node()` first, falls back to first file node's `absolutePath`.
- `_unwrap_file_entries`: parses file independently from project AST; writes regenerated code using `PrettyPrinter`.
- `_inject_require` adds `require_once __DIR__ . '/beluga_runtime.php';` via text replacement after `<?php` tag.
- `_remove_require` removes the `require_once` line during deinstrumentation; called after AST-based probe unwrap since PrettyPrinter re-emits the `require_once` from the parsed AST.
- Registry mode: precise restoration using `.beluga_registry.json`. Scan mode: fail-safe by scanning all `.php` files.
- Both deinstrumentation modes call `_remove_require` on each file after unwrapping `__logic_var` calls.
