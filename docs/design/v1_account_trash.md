# V1 Account Trash

## Decision

V1 account removal uses a reversible trash state rather than hard deletion.
Trashing an account disables sign-in and preserves its financial and audit
history. Administrators can restore accounts; restored accounts remain
inactive until explicitly reactivated. Accounts cannot be permanently purged.

## Implementation

- Add a nullable `trashed_at` timestamp to users.
- Add administrator-only account trash and restore actions with CSRF
  protection and audit-log entries.
- Remove trashed accounts from Manage accounts and prevent trashing the signed
  in administrator or the last active administrator.
- Keep account-linked transactions, proofs, receipts, reversals, and audit
  rows intact.
