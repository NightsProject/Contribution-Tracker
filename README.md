# Contribution & Expense Tracker

Foundation for the role-based shared-pool tracker described in
[`docs/design/contribution_expense_tracker_design_document.docx`](docs/design/contribution_expense_tracker_design_document.docx).
The application currently includes the FastAPI foundation, PostgreSQL
persistence, database-backed sessions, Argon2id authentication, role-protected
account management, contribution submissions and review, private proof-image
storage, and versioned Alembic migrations. Expense workflows are not
implemented yet.

## Run locally with Docker Compose

```sh
cp .env.example .env
docker compose up --build
```

The web service is available at <http://localhost:8000>; `/healthz` provides a
liveness check. Compose runs database migrations before starting the web
service and persists PostgreSQL data and uploads in named volumes.

The credentials in `.env.example` are for local development only. Replace them
with strong, unique values before using any non-local deployment. For an
HTTPS-terminated deployment, set `SESSION_COOKIE_SECURE=true`.

Create the first administrator after the database is running:

```sh
docker compose exec web python -m app.cli create-admin
```

The command prompts for the administrator details and password, and refuses to
create a second active bootstrap administrator. Administrators can create,
update, deactivate, or change the roles/passwords of accounts from
**Manage accounts** in the dashboard. Passwords must be at least 12 characters.

Signed-in users can submit contributions with a PHP amount, payment reference,
payment date, and optional JPEG/PNG/WebP proof image. Proof files are size- and
content-validated, normalized, stored outside the public static directory, and
served only to the submitting user or an administrator. Administrators review
pending submissions from **Review contributions**; approval or rejection and
its audit entry are committed atomically. Only approved submissions count as
posted contributions.

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
