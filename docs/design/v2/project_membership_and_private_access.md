# Project Membership and Private Access

## Decision

Projects support an owner, a co-owner role, and members. Public projects are
discoverable and open to direct opt-in by active users. Private projects stay
hidden and are joined through an accepted username invitation or an active
owner-controlled join link.

## Implementation

- The project creator becomes its initial owner.
- Represent project membership and role explicitly, with a uniqueness
  constraint preventing duplicate membership for the same project and user.
- Public project discovery allows active users to opt in and submit payments
  without owner approval. Whether opt-in creates persistent membership or
  only enables payment submission remains open. Payment review is separate
  from joining.
- A private username invitation does not grant access until the recipient
  accepts it.
- Joining through an active private link grants membership directly, without
  a separate owner approval step.
- Enforce membership and role checks in every private project page, financial
  query, state-changing route, and private file response.
- Do not show private projects or their membership in public directory,
  profile, or search results.

## Open questions

- How co-owners are appointed and whether there is a limit.
- Who can remove members or revoke invitations, and what happens to pending
  payments when a member is removed.
- Whether accepted invitations and memberships can be revoked or leave
  history retained.
- Invitation expiration and revocation policy.
