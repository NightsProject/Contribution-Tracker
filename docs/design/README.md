# Design Decisions Index — Contribution Tracker

This directory contains **one file per design decision** for Contribution Tracker. Each decision is self-contained and traceable to implementation.

## Decision Files

| File | Decision Area | Status |
|------|---------------|--------|
| `initial_admin_bootstrap.md` | First administrator creation flow | ✅ Implemented |
| `public_user_signup.md` | Public user registration | ✅ Implemented |
| `decision-public-landing-anonymous-contributions.md` | Public landing page & anonymous contributions | ✅ Implemented |
| `v1_account_trash.md` | Account trash and restore | ✅ Implemented |
| `v1_financial_corrections.md` | Financial corrections (void, refund, reverse) | ✅ Implemented |
| `shared_ui_styling.md` | Shared UI styling approach | ✅ Implemented |
| `uv_project_tooling.md` | UV project tooling adoption | ✅ Implemented |
| `v2/README.md` | Version 2 design overview | 📋 Planned |
| `decision-risks.md` | Identified risks & mitigations | 🟡 Create as needed |
| `decision-open-questions.md` | Deferred decisions | 🟡 Create as needed |
| `decision-<topic>.md` | Additional domain-specific decisions | 🟢 Add during implementation |

**Legend**: ✅ Implemented | 📋 Planned | 🟡 Conditional | 🟢 As-needed

## Convention

- **One decision per file** — named `decision-<short-kebab-case>.md` (v1) or descriptive names
- **Sections**: Context, Decision, Consequences, Alternatives Considered, Status, Implementation Notes
- **Update existing file** when implementation changes a decision
- **Add new file** when implementation introduces a new decision
- **Reference in commits**: `feat(<area>): <desc> per decision-<x>.md decision-<y>.md`

## Required First Decisions (create before Phase 1)

1. **Product Boundary** — What the application does/doesn't do
2. **Persistence** — PostgreSQL + SQLAlchemy + Alembic
3. **Data Design** — Core entities, IDs, timestamps, soft delete
4. **Testing** — Test layers, acceptance criteria as tests
5. **Roadmap** — Phased implementation with exit criteria

## Template

Use `decision-TEMPLATE.md` as the starting point for each new decision.

## Legacy Sources

- Original design document: `contribution_expense_tracker_design_document.docx`
- This index and decision files are the **canonical current design**

---

*Created: November 06, 2026 | Project: Contribution Tracker*