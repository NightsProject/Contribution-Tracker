# Decision: Open Questions — Contribution Tracker

## Context
Key integration points or design choices that are not yet decided. These should be resolved before the phase that depends on them.

## Open Questions

### V2 Project Lifecycle (Target: Phase 1)
**Context**: Project creation, archival, and deletion rules needed before implementing V2 project features.

**Options**:
1. **Projects can be archived but not deleted** — Retains all history, prevents accidental data loss / Adds UI complexity for archived state
2. **Projects can be soft-deleted** — Similar to account trash pattern / Requires restore logic
3. **Projects are permanent once created** — Simplest / No cleanup for abandoned projects

**Investigation Needed**:
- Check if account trash pattern works for projects
- Determine if any legal/retention requirements exist

**Decision Target**: Before Phase 1 implementation begins.

---

### V2 Co-owner Cardinality (Target: Phase 1)
**Context**: Whether a project can have multiple co-owners or just one.

**Options**:
1. **Single co-owner** — Clear review responsibility / Limits collaboration
2. **Multiple co-owners** — More flexible / Complex review routing (who reviews owner's submission?)

**Investigation Needed**:
- Review v2/README.md open questions section
- Consider audit trail clarity

**Decision Target**: Before Phase 1 implementation begins.

---

### V2 Expense Policy (Target: Phase 2)
**Context**: Who can create/post project expenses, whether they need review, and insufficient funds behavior.

**Options**:
1. **Owner/co-owner create, no review, block on insufficient funds** — Simple / Risk of overspend if not checked
2. **Owner/co-owner create, co-owner reviews owner's, block on insufficient** — Mirrors contribution review / More complex
3. **Admin-only for now** — Defer to later / Not self-service for project owners

**Investigation Needed**:
- Review v2/project_expense_ledger.md
- Check v1 expense pattern for consistency

**Decision Target**: Before Phase 2 implementation begins.

---

## Resolved Questions (move here when decided)

---

## Convention
- Keep this file updated as questions are resolved
- When resolved, move to "Resolved Questions" section
- Create a new `decision-<topic>.md` for the final decision
- Update `docs/design/README.md` table
- Reference in phase plan where the decision unblocks work