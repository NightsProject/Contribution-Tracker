# Version 2 Design

## Status and release boundary

This folder captures the agreed product direction and proposed implementation
for version 2. Version 1 is the current stable release and must remain
unchanged. Version 2 work is to be developed on a separate branch based on the
stable v1 baseline; this document does not create that branch or change
application code.

The existing baseline specification remains
[`../contribution_expense_tracker_design_document.docx`](../contribution_expense_tracker_design_document.docx).
These v2 decisions extend that baseline without changing v1 behavior.

## Product goal

Let active registered users create projects, organize public or private
participation, submit payment records with proof, and track project-specific
income and expenses. A project balance is separate from the existing shared
pool.

## Agreed behavior

- A project has an owner and supports a co-owner role; whether multiple
  co-owners are supported remains open.
- Public projects can be discovered in a project directory and on their
  creator's profile. Any active registered user can opt in and submit payments
  to a public project without owner approval; whether opt-in creates persistent
  membership remains open.
- Private projects are not listed in directories or public profiles. Owners
  can invite users by username; invitees must accept an invitation.
- A private-project join link allows direct joining while active. It is
  reusable, has no expiry, and the owner can activate or deactivate it.
- Users submit a project payment through the app with amount, payment date,
  payment reference, and optional proof image.
- A project owner reviews payment submissions. A co-owner reviews a payment
  submitted by the project owner; submitters cannot approve their own
  payments.
- Projects track their own expenses as well as contributions.
- Project balances and transactions do not affect the v1 shared pool.

## Proposed user flows

### Project creation and discovery

1. A signed-in user creates a project and chooses public or private visibility.
2. The creator becomes the initial owner.
3. Public projects appear in the directory and creator profile. Any active
   user can opt in and submit a project payment without owner approval;
   whether this creates persistent membership remains open.
4. Private projects do not appear in public discovery surfaces. The owner
   invites a user by username, or shares an active join link.
5. An invitee accepts an invitation before becoming a member. A user with an
   active join link becomes a member directly.

### Payment submission and review

1. An eligible user selects a project and submits amount, payment date,
   reference, and optional proof.
2. The submission is pending and does not change the project's available
   balance.
3. An authorized owner approves or rejects the submission. A project owner
   cannot review their own submission; a co-owner reviews that submission.
4. Only approved payments count toward the project balance. Rejection reason,
   reviewer, and review time are retained.

### Project expenses

Project expenses are recorded against exactly one project and reduce only that
project's balance once posted. Who may create or post them, whether they need
review, and whether insufficient funds block them are open policy decisions;
see [Project Expense Ledger](project_expense_ledger.md).

## Proposed domain model

These are logical entities, not a finalized physical schema:

- **Project**: owner, name, description, visibility, lifecycle state, and
  timestamps.
- **Project membership**: project, user, role (`OWNER`, `CO_OWNER`, or
  `MEMBER`), and membership state. Enforce one membership per project/user;
  co-owner cardinality remains a policy question.
- **Project invitation**: project, invitee, inviter, state, and audit
  timestamps. Invitations require acceptance before membership is granted.
- **Project join link**: project, a securely stored token verifier, active
  state, and activation/deactivation metadata. A valid active link directly
  creates membership.
- **Project contribution**: project, submitting user, positive amount in
  integer centavos, payment date/reference, optional private proof key, review
  state, reviewer, and review timestamps.
- **Project expense**: project, positive amount in integer centavos, expense
  date, description/category, optional private receipt key, posting state, and
  actor/review metadata as policy requires.

Prefer project-specific financial records and posting services over making
project transactions nullable variants of v1 shared-pool records. This keeps
v1 accounting queries isolated and makes the project ledger's authorization
and lifecycle explicit.

## Ledger rules

- Project balance is derived from approved project contributions minus posted
  project expenses; pending and rejected records do not affect it.
- Store monetary values as integer centavos.
- Serialize balance-changing operations per project so concurrent approvals
  and expenses cannot overspend or post the same financial transition twice.
- Record financial state changes and membership/ownership changes in the
  existing audit log pattern. Do not log raw invitation or join-link tokens.
- Never include project contributions or expenses in shared-pool summaries,
  transaction queries, or recurring-expense calculations.
- Reversals/corrections must remain auditable and must not rewrite financial
  history silently.

## Privacy and authorization

- Public profiles expose only the username, display name, and public-project
  information needed for discovery; never expose email or private-project
  membership.
- Private project pages, membership, invitations, financial activity, proof,
  and receipts require project-scoped authorization. Return not-found behavior
  where necessary to avoid revealing private project existence.
- Project proof and receipt files stay outside public static storage and are
  served only after checking access to the associated project and record.
- Every state-changing browser request uses the existing CSRF protections.
- Only active users may discover/join projects or submit payments.

## Decisions and open questions

Decision records:

- [V2 Release Boundary](release_boundary.md)
- [Project-Scoped Ledgers](project_scoped_ledgers.md)
- [Usernames and Public Project Discovery](usernames_and_public_discovery.md)
- [Project Membership and Private Access](project_membership_and_private_access.md)
- [Private Join-Link Control](private_join_links.md)
- [Project Payment Review](project_payment_review.md)
- [Project Expense Ledger](project_expense_ledger.md)

Resolve these policy questions before implementing the affected workflows:

1. What project fields are required at creation, and can a project be closed,
   archived, or deleted?
2. How is a co-owner selected, and can a project have more than one?
3. Can an owner or co-owner revoke a membership or invitation, and what
   happens to that person's pending submissions?
4. Do public participants become members automatically, or can they submit
   without persistent membership?
5. How long do username invitations remain valid, and can an owner revoke
   them?
6. May a project have multiple join links? Does deactivation apply to all
   links or only the selected link?
7. Who may create, review, approve, and reverse project expenses? Should a
   posted expense be rejected when it exceeds the available project balance?
8. Who reviews a co-owner's own payment submission? The agreed rule covers the
   project owner's own submission, which a co-owner reviews.
9. Are payment instructions and QR details configured per project, inherited
   from the app, or omitted?
10. Are project goals, target dates, project-specific recurring expenses, and
    member notifications in scope for the first v2 release?

## Implementation sequence

1. Confirm the open authorization, lifecycle, and expense policies above.
2. Create the v2 branch from the stable v1 baseline.
3. Add additive schema migrations and tests proving v1 shared-pool isolation.
4. Implement usernames, projects, membership, invitations, and join-link
   authorization.
5. Implement project contribution submission, private proof access, and
   project-owner review.
6. Implement project expenses and per-project balance serialization according
   to the confirmed policy.
7. Add project discovery/profile pages, project ledger views, audit coverage,
   and end-to-end authorization/accounting tests.
8. Update deployment, backup, and user documentation before the v2 release.

## Minimum acceptance criteria

- V1 shared-pool totals and existing contribution/expense behavior are
  unchanged by project activity.
- Public users can discover a public project and submit a payment; private
  project details do not leak through directories, profiles, searches, or
  unauthorized record/file URLs.
- Username invitations grant membership only after acceptance.
- An active private link grants direct membership; a deactivated link grants
  none. Links do not expire and are reusable while active.
- Project payment submission, approval, rejection, and proof access enforce
  project-scoped permissions.
- A submitter cannot approve their own payment; a co-owner can review the
  owner's submission.
- Project balances include only approved contributions and posted expenses,
  and concurrent balance changes preserve ledger correctness.
- Financial and access-control changes are auditable without storing secrets
  or leaking private financial data.
