# BELUGA LEMUR

This repository contains the BELUGA LEMUR instrumentation module.

## Manage with `uv`

This project is initialized for use with `uv` (https://astral.sh/uv).

Quick start:

```bash
# install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# initialize a uv project (creates or updates pyproject.toml)
uv init .

# add the dependency (constraining to >=1.2.1)
uv add "php-parser-py>=1.2.1"

# generate lockfile
uv lock

# install dependencies into .venv
uv sync
```

The project manifest `pyproject.toml` already declares `php-parser-py>=1.2.1`.

