# PORIFERA: Php cOde Rewriting Instrumentation For ExpRession in Ast

> Porifera (Sponges) are the oldest porous filter-feeding organisms in the ocean. Sponges draw in seawater through micro-pores throughout their bodies, filter it, and capture nutrients. 
> PORIFERA uses this as a metaphor: Like the pores of a sponge, it permeates each expression in the code, silently absorbing runtime values without altering the behavior of the program itself.

PHP AST instrumentation library. Injects runtime probe wrappers around target PHP expressions to capture their values, then restores the original code.

Requires Python >=3.11,<3.13.

## Installation

```bash
pip install porifera
```

## Quick Start

```python
from php_parser_py import Parser
from porifera import instrument, deinstrument

# Parse PHP project
ast = Parser().parse_file("path/to/project/index.php")

# Define targets: AST node_id -> expr_key label
targets = {
    "node_42": "user_query",
    "node_87": "config_value",
}

# Instrument — wraps targets with probe calls
modified_files = instrument(targets, ast)

# Optionally specify output directory for probe logs
# modified_files = instrument(targets, ast, output_dir=Path("/tmp/logs"))

# Run PHP project... probes log to .porifera_data_<timestamp>.jsonl

# Deinstrument — restores original code
restored_files = deinstrument(ast)
```

After instrumentation, a PHP expression like:

```php
$row = $db->query($sql);
```

becomes:

```php
$row = __porifera_probe_a1b2c3d4("user_query", $db->query($sql));
```

The probe returns the original value transparently and logs it to `.porifera_data_<timestamp>.jsonl`. Each instrumentation run produces a unique timestamped file to avoid overwriting previous data.

## Examples

### Log all array access values at runtime

Probe every `$config['db_host']`, `$row['name']`, etc.:

```python
from php_parser_py import Parser
from porifera import instrument

ast = Parser().parse_file("app/config.php")

# All Expr_ArrayDimFetch nodes -> targets
fetches = ast.nodes(lambda n: n.node_type == "Expr_ArrayDimFetch")
targets = {n.id: f"array_{n.id[:8]}" for n in fetches}

instrument(targets, ast)
```

### Log all function call return values

Probe every function call:

```python
from php_parser_py import Parser
from porifera import instrument

ast = Parser().parse_file("app/service.php")

# All Expr_FuncCall nodes -> targets
calls = ast.nodes(lambda n: n.node_type == "Expr_FuncCall")
targets = {n.id: f"call_{n.id[:8]}" for n in calls}

instrument(targets, ast)
```

### Log specific function call return values

Probe only `mysqli_query(...)` calls:

```python
from php_parser_py import Parser
from porifera import instrument

ast = Parser().parse_file("app/db.php")

# All Expr_FuncCall nodes
calls = ast.nodes(lambda n: n.node_type == "Expr_FuncCall")

# Filter by function name
targets = {}
for call in calls:
    name_node = next(ast.succ(call, lambda e: e.get("field") == "name"), None)
    if not name_node or name_node.get_property("parts") != ["mysqli_query"]: continue
    targets[call.id] = f"query_{call.id[:8]}"

instrument(targets, ast)
```

### Broader coverage with ElevatingProbeStrategy

`StandardProbeStrategy` skips lvalue targets (e.g. `$i` in `$i++`). `ElevatingProbeStrategy` wraps the nearest safe ancestor instead:

```python
from porifera import instrument, ElevatingProbeStrategy

instrument(targets, ast, strategy=ElevatingProbeStrategy())
```

## Documentation

- [Design Specification](docs/design.md) — API signatures, class responsibilities, strategies, exceptions, and validation rules
- [Implementation Notes](docs/impl.md) — php-parser-py API reference, AST node types, unsafe wrap contexts, and developer instructions
- [AST Structure](https://github.com/jhu-seclab-beluga/php-parser-py/blob/main/docs/libs/php_parser_ast.md) - the structure of the php-parser-py AST, node types, and properties, and how to navigate it.

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Type checking
uv run mypy src/

# Linting
uv run pylint src/

# Formatting
uv run black src/ tests/
uv run isort src/ tests/
```
