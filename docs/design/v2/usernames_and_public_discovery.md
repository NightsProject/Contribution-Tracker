# Usernames and Public Project Discovery

## Decision

Add a unique username to support project invitations and profile discovery.
Public projects are discoverable in a project directory and on their creator's
public profile. Private projects never appear in public discovery surfaces.

## Implementation

- Require usernames to be unique under a documented case-normalization rule.
  Enforce uniqueness in the database, not only in form validation.
- Use usernames for user lookup and invitations; do not use or disclose email
  addresses as public identifiers.
- Let a profile show the username, display name, and public projects needed
  for project discovery. Do not expose email, private-project membership,
  invitations, or private financial information.
- Include only public, active projects in the public directory and creator
  profile. Apply project visibility predicates in server-side queries, not
  only in templates.
- Active users can opt in to a public project and submit payments without
  project-owner approval. Whether opt-in creates persistent membership or
  only enables payment submission remains open.
- Only active registered users may use project discovery and contribution
  flows.

## Open questions

- Whether usernames are chosen at sign-up or added later to existing
  accounts, and how existing accounts are prompted to choose one.
- Username length, allowed characters, reserved words, and rename policy.
- Whether profile display names can be hidden or changed independently of
  usernames.
