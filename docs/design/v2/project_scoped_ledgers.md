# Project-Scoped Ledgers

## Decision

Each project has an independent financial ledger containing project
contributions and project expenses. Project transactions never enter the
existing v1 shared pool.

## Implementation

- Model project contributions and project expenses as project-scoped financial
  records with explicit project foreign keys. Prefer separate project record
  types/tables over making shared-pool records ambiguously project-aware.
- Store all amounts as positive integer centavos; represent expense deductions
  in balance calculations rather than storing negative amounts.
- Derive a project's available balance from approved contributions and posted
  expenses. Pending or rejected records do not affect the balance.
- Use a project-scoped serialization mechanism for concurrent approvals and
  expense posting. Do not rely on a read-then-write balance check without a
  lock or equivalent transaction guarantee.
- Keep v1 queries and accounting services restricted to v1 shared-pool
  records. Add regression tests that create project activity and assert v1
  totals remain unchanged.
- Preserve financial history with auditable review, posting, and reversal
  records. Do not silently edit or delete posted transactions.

## Open questions

- Whether the project ledger permits a negative balance or rejects expenses
  that exceed available funds.
- The project expense creation, approval, and reversal permissions.
- Whether project payment instructions/QR configuration are project-specific.
- Whether project recurring expenses are part of the initial v2 release.
