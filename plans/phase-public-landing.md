# Plan: Public Landing Page & Anonymous Contributions

## Goal and Scope
Implement a public landing page at `/` that allows anonymous visitors to view the pool summary, transaction history, and submit contributions for admin review. The root route previously redirected to `/dashboard` (auth-required); now it serves a public page.

**Non-goals:**
- V2 project features (projects, memberships, join links)
- Changes to authenticated dashboard or admin flows
- Database schema changes (no migration needed)

## Acceptance Criteria
- [ ] `GET /` returns 200 with public landing page (hero, pool summary, contribution form, transaction history with filters/pagination)
- [ ] `POST /` accepts anonymous contribution submissions (amount, reference, date, optional proof image)
- [ ] Submissions create `Contribution` with `status=PENDING`, attributed to anonymous user, with audit log entry
- [ ] Public transaction history shows only `APPROVED` contributions and `POSTED` expenses
- [ ] Header shows "Sign in" link on public page; sidebar/header for authenticated pages unchanged
- [ ] All existing tests pass; new test `test_root_serves_landing_page` passes

## Relevant Decisions
- `decision-public_user_signup.md` — public sign-up flow (related but separate)
- `shared_ui_styling.md` — consistent styling approach
- `docs/design/README.md` — decision index

## Implementation Steps

| Step | Files | Description |
|------|-------|-------------|
| 1 | `app/config.py` | Refactor `database_url` to computed field from discrete Postgres settings; add `web_port`, `app_domain`; allow extra env vars |
| 2 | `app/auth.py` | Add `public_session` dependency: gets/creates session without requiring auth |
| 3 | `app/main.py` | Include `public.router`; remove root redirect to `/dashboard` |
| 4 | `app/routes/public.py` (new) | Public router with `GET /` (landing) and `POST /` (submit contribution) |
| 5 | `app/templates/landing.html` (new) | Public landing template extending `base.html` |
| 6 | `app/templates/partials/header.html` | Add `is_public_page` branch with minimal header + "Sign in" link |
| 7 | `app/static/app.css` | Add public page styles: hero, contribution form, summary cards, responsive header |
| 8 | `tests/test_health.py` | Replace `test_root_redirects_to_dashboard` with `test_root_serves_landing_page` |

## Verification Commands
```bash
# Focused test
uv run pytest tests/test_health.py::test_root_serves_landing_page -v

# Full suite
uv run pytest -x

# Lint/check
git diff --check
```

## Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Anonymous session handling conflicts with auth | `public_session` is independent; `current_session` still requires auth |
| Proof upload path traversal | `store_private_image` validates content, normalizes paths, stores outside static |
| Pool balance concurrency | `get_pool_balance` uses existing accounting lock |
| XSS via contribution reference/description | Jinja2 auto-escapes; template uses `{{ }}` not `|safe` |

## Open Questions (track in `decision-open-questions.md`)
- None for this phase — all decisions resolved in implementation

## Progress
- [x] Step 1: Config refactor
- [x] Step 2: `public_session` dependency
- [x] Step 3: Main router update
- [x] Step 4: Public routes module
- [x] Step 5: Landing template
- [x] Step 6: Header partial
- [x] Step 7: Public CSS
- [x] Step 8: Test update
- [x] All tests pass (59/59)