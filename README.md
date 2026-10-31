# Contribution & Expense Tracker

Foundation for the role-based shared-pool tracker described in
[`docs/design/contribution_expense_tracker_design_document.docx`](docs/design/contribution_expense_tracker_design_document.docx).
The application currently includes the FastAPI foundation, PostgreSQL
persistence, database-backed sessions, Argon2id authentication, role-protected
account management, contribution submissions and review, private proof-image
storage, a centralized accounting service with serialized pool updates,
balance queries, audited posting/reversal operations, admin expense entry with
private receipt storage, recurring expense schedule management and worker
processing, and versioned Alembic migrations.

## Run locally with Docker Compose

```sh
cp .env.example .env
# Edit .env and set a unique, random POSTGRES_PASSWORD before starting.
docker compose up --build
```

Generate a URL-safe database password with `openssl rand -hex 32` and put the
result in `.env`; the value is used in the SQLAlchemy connection URL.

The web service is available at <http://localhost:8000>; `/healthz` provides a
liveness check. Compose runs database migrations before starting the web
service and persists PostgreSQL data and uploads in named volumes. The web
port binds to localhost only; PostgreSQL is not published to the host.

For HTTPS deployment, point the domain in `APP_DOMAIN` at the server, set
`SESSION_COOKIE_SECURE=true`, and start the optional Caddy proxy profile:

```sh
docker compose --profile production up --build -d
```

Caddy obtains and renews TLS certificates automatically. Expose only ports 80
and 443 publicly; keep port 8000 bound to localhost. Do not use the example
password in a deployed environment.

When the database is initialized and has no administrator account, open the
application and choose **Create the first administrator** on the sign-in page.
The one-time setup form creates the account and signs it in. The setup link is
disabled as soon as an administrator account exists.

Alternatively, create the first administrator from the command line:

```sh
docker compose exec web uv run --no-sync python -m app.cli create-admin
```

The command prompts for the administrator details and password and refuses to
create an administrator if one already exists. Administrators can create,
update, deactivate, or change the roles/passwords of accounts from
**Manage accounts** in the dashboard. Administrators can move accounts to
**Trash** and restore them; trashed accounts are inactive, and their financial
history is retained. Pending contributions can be voided, approved contributions
recorded as refunded, and posted expenses reversed with a required reason.
These corrections are audited and update the pool balance where applicable;
they do not initiate external payments. Passwords must be at least 12
characters.

Visitors can also sign up from the sign-in page. New accounts are immediately
active contributor accounts with the `USER` role and are signed in after
creation; public sign-up cannot grant administrator access.

Signed-in users can submit contributions with a PHP amount, payment reference,
payment date, and optional JPEG/PNG/WebP proof image. Proof files are size- and
content-validated, normalized, stored outside the public static directory, and
served only to the submitting user or an administrator. Administrators review
pending submissions from **Review contributions**; approval or rejection and
its audit entry are committed atomically. Only approved submissions count as
posted contributions.

Administrators can record expenses from **Expense history**. The server checks
the current pool balance under the accounting lock before posting, records an
audit entry, and optionally stores a validated private receipt image. Signed-in
users can review the posted expense history.

Administrators can create and manage recurring expense schedules from
**Recurring expenses**. A dedicated APScheduler worker processes occurrences
in chronological order, posts them only when funds are available, and exposes
blocked occurrences for manual retry. Compose starts the worker only after the
web service has applied database migrations.

The dashboard summarizes the shared pool, displays contribution payment
instructions and QR details, and provides a paginated transaction history with
account, type, status, text, and date filters. Administrators manage payment
details and QR uploads from **Payment settings**; QR files are private and
visible only to signed-in users.

## Backups and recovery

Back up the database and uploads together. The script briefly stops the web
and scheduler services to capture a consistent pair, then restarts only the
services that were running before the backup:

```sh
./scripts/backup.sh /var/backups/contribution-tracker
```

Backups include SHA-256 checksums. Store them off-host with access controls and
retention appropriate to your organization, and encrypt them at rest and in
transit. To schedule daily backups on a
Linux host, adjust the paths in `deploy/contribution-tracker-backup.service`,
then install and enable the provided systemd service and timer:

```sh
sudo cp deploy/contribution-tracker-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now contribution-tracker-backup.timer
```

To restore, stop web and scheduler, verify the manifest, and explicitly
acknowledge that the database will be replaced:

```sh
docker compose stop web scheduler
(
  cd /var/backups/contribution-tracker
  sha256sum --check TIMESTAMP-SHA256SUMS
)
CONFIRM_RESTORE=yes \
BACKUP_CHECKSUMS=/var/backups/contribution-tracker/TIMESTAMP-SHA256SUMS \
  /opt/contribution-tracker/scripts/restore.sh \
  /var/backups/contribution-tracker/TIMESTAMP-database.dump \
  /var/backups/contribution-tracker/TIMESTAMP-uploads.tar.gz
docker compose up -d
```

Periodically restore a backup into a separate test environment and verify
login, transaction history, private proof/receipt/QR access, and scheduler
recovery before relying on backups for production recovery.

## Run tests

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.
The committed `uv.lock` pins the resolved dependencies for local development
and container builds.

```sh
uv sync --all-groups
uv run pytest
```

## Database migrations

Create a new migration after changing the SQLAlchemy models:

```sh
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
```

Set `DATABASE_URL` when running Alembic outside Compose. The default targets a
local PostgreSQL instance; Compose supplies the service hostname automatically.
