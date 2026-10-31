# Project Tooling with uv

## Decision

Use `uv` as the sole Python dependency manager and project command runner.
Declare runtime and development dependencies in `pyproject.toml` and commit
`uv.lock` so local development and container builds use the same resolved
versions.

## Implementation

- Local setup installs all dependency groups with `uv sync --all-groups`;
  project commands and tests run through `uv run`.
- Docker images install locked runtime dependencies with `uv sync --frozen
  --no-dev`, and Compose service commands use `uv run --no-sync`.
- Legacy pip requirements files are removed.
