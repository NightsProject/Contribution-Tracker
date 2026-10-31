# Project Expense Ledger

## Decision

Projects track project-specific expenses as well as contributions. Posted
project expenses reduce only the corresponding project's balance and never
affect the v1 shared pool.

## Implementation

- Give every project expense an explicit project association, positive amount
  in integer centavos, date, description/category, actor, posting state, and
  audit history. Support a private receipt file if the product policy requires
  one.
- Include an expense in the project's balance only after its posting
  transition succeeds.
- Serialize posting against other balance-changing operations for the same
  project and make duplicate posting impossible.
- Apply project-scoped authorization to expense history, mutation routes,
  and private receipt access.
- Do not use the v1 administrator-only expense route for project expenses
  without an explicit policy decision. Do not count project expenses in
  shared-pool or recurring-expense calculations.

## Open questions

- Which roles may create, approve, post, reverse, or view project expenses?
- Does a project expense require approval, and if so, can its submitter review
  it?
- Are expenses blocked when they exceed the available project balance?
- Are receipts required or optional, and who can view them?
- Are recurring project expenses needed in the first v2 release?
