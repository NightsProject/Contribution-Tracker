# V2 Release Boundary

## Decision

Keep v1 as the stable release and implement v2 on a separate branch based on
the v1 stable baseline. Do not introduce the v2 project feature into the v1
stable branch.

## Implementation

- Treat v1 behavior, especially the shared-pool ledger, as a compatibility
  boundary.
- Make v2 schema changes additive and prove that existing v1 records and
  accounting queries retain their current meaning.
- Keep v2 documentation and implementation decisions under the v2 design
  area so they do not silently redefine v1 decisions.
- Before release, document the v2 migration, deployment, backup, and rollback
  expectations.

The v2 branch name, branching procedure, and stable release tag are not yet
specified. This decision record documents the requested separation; it does
not create a branch or tag.
