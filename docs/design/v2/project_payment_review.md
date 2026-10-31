# Project Payment Review

## Decision

Users submit project payments in the app. A project owner reviews submissions;
a co-owner reviews a submission made by the project owner. No user may approve
their own submission.

## Implementation

- A submission records the project, submitting user, amount in integer
  centavos, payment date, payment reference, optional proof image, status,
  reviewer, review time, and rejection reason.
- Treat payment submission as a claim pending review, not as posted project
  funds. Only approval posts the contribution to the project's available
  balance.
- Preserve the existing contribution lifecycle concepts: pending, approved,
  rejected, and reversed. Define any status changes as audited state
  transitions.
- Authorize review against the project's ownership roles on the server for
  every review request. A global administrator role does not automatically
  grant project ownership or access to private project proof.
- Reject self-review even if the submitting user otherwise has a review role.
  A co-owner may review the project owner's submission.
- Keep proof images in private storage and authorize access using project
  membership/ownership and submission permissions.
- Commit approval and its audit event atomically; serialize balance-changing
  approval with other operations on the same project.

## Open questions

- Who reviews a co-owner's own payment submission.
- Whether a global administrator has a documented emergency-review role.
- Whether members can see other contributors' references, proof, and
  rejection details or only aggregate/project-visible information.
- Whether there are any project-specific payment limits or duplicate-reference
  rules.
