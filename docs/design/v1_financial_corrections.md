# V1 Financial Corrections

## Decision

Financial transactions are not hidden in trash or deleted. Pending
contributions can be voided with a required reason. Approved contributions can
be refunded by reversing their ledger effect, provided the funds are still
available. Posted expenses can be reversed with a required reason. Reversals
are final, auditable financial corrections; a new correct transaction must be
entered separately when needed. Recording a contribution refund does not
initiate a payment transfer; an administrator handles any actual refund
outside the application.

## Implementation

- Record voided contributions with a distinct `VOIDED` status and a required
  reason. Voiding applies only to pending contributions and has no pool-balance
  effect.
- Record refunds and expense reversals using `AccountingReversal`, retaining
  the reason and actor. Update the source status to `REVERSED`.
- Preserve the existing serialized accounting lock and reject contribution
  refunds when the funds have already been spent.
- Show available correction actions only for pending contributions, approved
  contributions, and posted expenses. Require CSRF-protected admin requests.
- Show correction reasons in transaction history and preserve them in the
  audit/reversal records.
- The migration removes transaction trash timestamps, making any previously
  hidden rows visible again without changing their status or balance effect.
  Administrators can then make an explicit correction with a reason if needed.
