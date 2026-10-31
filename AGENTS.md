# Project Guidelines

## Design Decisions and Implementations

- Before implementing a feature or changing application behavior, review the design material in `docs/design/`.
- Record each implementation decision in its own file under `docs/design/`. One file must describe one decision and its implementation; do not combine unrelated decisions in one file.
- Add a new decision file when the implementation introduces a new decision. Edit the existing file when it implements or changes a decision already documented there.
- Keep the design record aligned with the delivered behavior, including meaningful deviations from the source design document.

## Project Overview

- This is a FastAPI application using Jinja2 templates, SQLAlchemy, PostgreSQL, and Alembic migrations.
- Follow existing application patterns and keep financial amounts as integer centavos.
- Treat user-submitted proof, receipt, and payment QR files as private; preserve the existing authorization checks for access.

## Validation

- Run the focused tests for the changed behavior with `uv run pytest`, then the full test suite when practical.
- For database model changes, create an Alembic migration and verify migrations remain compatible with the existing schema.
- Run `git diff --check` before completing changes.
