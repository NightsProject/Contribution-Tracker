# Initial Administrator Bootstrap

## Decision

Provide a one-time browser setup flow for the first administrator, alongside
the existing `create-admin` command. The setup link appears on the sign-in page
only while no administrator account exists. The setup endpoint also checks
this condition when rendering and submitting the form.

## Implementation

- `GET /setup` creates or reuses an anonymous session so the form is protected
  by the application's existing CSRF mechanism.
- The form validates the name, email, password length, and password
  confirmation. Passwords use the existing Argon2id hashing configuration.
- Successful setup writes the administrator and audit event in one transaction
  and signs the new administrator in.
- Browser setup and `create-admin` share the existing accounting singleton
  lock while checking and creating the first administrator. This serializes
  competing bootstrap attempts across application processes without a schema
  migration.
- Any existing administrator account, active or inactive, closes browser
  setup. Rejected or stale setup requests cannot create another administrator.

## Operational Note

The setup page is intentionally unauthenticated until the first administrator
is created. Complete initial setup promptly and ensure the application is
reachable only by trusted operators during that period.
