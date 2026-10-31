# Private Project Join Links

## Decision

An owner-controlled private-project join link is reusable and has no expiry.
While active, it allows direct joining without an additional owner approval.
The owner can activate or deactivate the link.

## Implementation

- Treat the URL as a bearer credential: use a cryptographically random,
  high-entropy token and store only a verifier/hash in the database.
- Do not log, audit, or display the raw token after link creation. Redact it
  from application and proxy logs where possible.
- Check that the project is private and the link is active on every join
  attempt. A deactivated or invalid link must not disclose project details or
  grant membership.
- Make link activation/deactivation an authenticated, CSRF-protected,
  owner-authorized action and record the actor and timestamp in the audit log.
- A successful join creates a project membership directly. Repeated use by an
  existing member must not create duplicate memberships.
- Since links do not expire, deactivation must take effect immediately.

## Open questions

- Whether a project can have multiple links at once or only one current link.
- Whether owners can rotate/regenerate a link, and whether regeneration
  immediately invalidates previous links.
- Whether co-owners can activate/deactivate links or only the owner can.
- Whether link creation should require an explicit confirmation explaining
  that anyone with the link can join while it remains active.
