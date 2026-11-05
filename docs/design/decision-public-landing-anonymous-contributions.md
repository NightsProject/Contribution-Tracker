# Decision: Public Landing Page & Anonymous Contributions

## Context
The application originally redirected the root route (`/`) to `/dashboard`, which requires authentication. This prevented anonymous visitors from viewing the pool summary, transaction history, or submitting contributions. To support public visibility and community contributions without requiring accounts, we need a public landing page at `/` that:
- Shows the shared pool summary (balance, totals, contributor count)
- Displays a paginated, filterable transaction history of approved contributions and posted expenses
- Provides a contribution submission form for anonymous visitors
- Allows optional proof image upload with validation

## Decision
- The root route (`/`) serves a public landing page accessible without authentication.
- Anonymous visitors can submit contributions (amount, payment reference, payment date, optional proof image).
- Submissions are attributed to a special "Anonymous Contributor" user and created with `status=PENDING`.
- Only `APPROVED` contributions and `POSTED` expenses appear in the public transaction history.
- A new `public_session` dependency provides session handling for public pages (CSRF tokens, proof upload tracking) without requiring user authentication.
- The public page uses a minimal header showing only the app name and a "Sign in" link.

## Consequences
### Positive
- Community members can contribute without creating accounts
- Transparent pool visibility builds trust
- Lower barrier to entry for one-time contributors

### Negative
- Anonymous submissions require admin review before affecting pool balance
- Proof images from anonymous users consume storage
- Potential for spam submissions (mitigated by admin review gate)

### Neutral
- Existing authenticated dashboard at `/dashboard` unchanged
- Account signup flow at `/signup` remains separate
- Session cookies used for CSRF on public forms

## Alternatives Considered
| Alternative | Why Rejected |
|-------------|--------------|
| Require signup before contribution | Higher friction; loses one-time/casual contributors |
| Show pool summary but require login to submit | Partial visibility without participation feels incomplete |
| Allow anonymous contributions to auto-approve | Financial risk; no audit trail without review |

## Status
✅ Implemented

## Implementation Notes
**Key Files:**
- `app/routes/public.py` — new router with `GET /` and `POST /`
- `app/templates/landing.html` — new public landing template
- `app/auth.py` — `public_session` dependency added
- `app/main.py` — `public.router` included; root redirect removed
- `app/templates/partials/header.html` — `is_public_page` branch added
- `app/static/app.css` — public page styles (hero, form, summary cards, responsive header)

**Config Refactor** (`app/config.py`):
- `database_url` now a computed field from discrete Postgres settings (`postgres_db`, `postgres_user`, `postgres_password`, `postgres_host`, `postgres_port`)
- Added `web_port` and `app_domain` settings
- `extra="allow"` on model config for forward compatibility

**Anonymous User:**
- Special user with email `anonymous@contribution-tracker.local`, name "Anonymous Contributor"
- Created on-demand by `get_or_create_anonymous_user()`
- Dummy password hash (cannot log in)

**Validation:**
- Amount: positive centavos, max configurable
- Payment reference: required, max 200 chars
- Payment date: not in future
- Proof: JPEG/PNG/WebP, size limit, content-validated

**Tests:**
- `test_root_serves_landing_page` verifies public page renders correctly
- All 59 existing tests pass

---

*Decision date: 2026-11-06 | Author: Jake | Related: public_user_signup.md, shared_ui_styling.md*