# Contribution & Expense Tracker

Foundation for the role-based shared-pool tracker described in
[`docs/design/contribution_expense_tracker_design_document.docx`](docs/design/contribution_expense_tracker_design_document.docx).
The initial scaffold includes the FastAPI application, PostgreSQL persistence,
SQLAlchemy models, and versioned Alembic migrations. Authentication and the
financial workflows are not implemented yet.

## Run locally with Docker Compose

```sh
cp .env.example .env
docker compose up --build
```

The web service is available at <http://localhost:8000>; `/healthz` provides a
liveness check. Compose runs database migrations before starting the web
service and persists PostgreSQL data and uploads in named volumes.

The credentials in `.env.example` are for local development only. Replace them
with strong, unique values before using any non-local deployment.

## Run tests

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Database migrations

Create a new migration after changing the SQLAlchemy models:

```sh
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Set `DATABASE_URL` when running Alembic outside Compose. The default targets a
local PostgreSQL instance; Compose supplies the service hostname automatically.
