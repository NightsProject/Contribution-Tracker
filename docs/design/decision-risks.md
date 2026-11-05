# Decision: Risks and Mitigations — Contribution Tracker

## Context
Identified risks that could impact delivery, correctness, or operations. Each risk has a concrete mitigation strategy.

## Risks

| Risk | Impact | Mitigation | Owner / Phase |
|------|--------|------------|---------------|
| V2 schema migrations break v1 data | High | Additive-only migrations; test v1 isolation in CI | Phase 1 (V2) |
| Concurrent project balance updates overspend | High | Per-project serialization lock in accounting service | Phase 2 (V2) |
| Private project membership leaks via search/directory | High | Not-found responses for unauthorized access; audit all read paths | Phase 1 (V2) |
| Join link token storage/verification | Medium | Store hash/verifier only; never log raw tokens | Phase 1 (V2) |
| Recurring expense worker duplicates on restart | Medium | Unique constraint on (schedule, due_at); atomic claim | Phase 2 (V2) |

## Common FastAPI/PostgreSQL Risks (review each project)

| Risk | Impact | Mitigation | When to Address |
|------|--------|------------|-----------------|
| Database connection exhaustion under load | High | Pool sizing, timeouts, health checks | Phase 1 |
| SQL injection via dynamic queries | High | Use SQLAlchemy ORM/parameterized queries only | Phase 1 |
| Timezone/date edge cases | Medium | Use `zoneinfo`/`dateutil` for IANA tzdata; property-based tests for DST | Phase with dates |
| Concurrent background workers (scheduler) | Medium | Atomic claim (UPDATE ... RETURNING); unique constraints | Phase with scheduler |
| Large data set performance | Medium | Bounded horizons / pagination; indexes on query patterns | Phase with queries |
| CSRF protection bypass | High | Double-submit cookie pattern on all state-changing routes | Phase 1 |
| File upload path traversal | High | Validate extensions, normalize paths, serve via auth-checked endpoint | Phase 1 |

## Implementation-Discovered Risks (add as found)

| Risk | Discovered | Mitigation | Status |
|------|------------|------------|--------|
| Alembic autogenerate misses some model changes | 2026-10-31 | Review generated migrations; add explicit ops | Verified |
| Testcontainers Postgres slow in CI | 2026-10-31 | Use tmpfs, pre-populated fixture DB | Implemented |

## Convention
- Review this file at start of each phase
- Add new risks as discovered during implementation
- Each mitigation must have a test case
- Update status as mitigations are implemented/verified
- Document runbook entries for operational risks