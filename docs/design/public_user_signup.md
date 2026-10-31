# Public User Sign-up

## Decision

Allow visitors to create contributor accounts from the sign-in page. Sign-up
creates an immediately active `USER` account; administrator access remains
available only through initial administrator setup or an administrator's
account-management workflow.

## Implementation

- `GET /signup` renders a CSRF-protected form using the shared anonymous
  session flow. `POST /signup` validates the name, email, password length, and
  password confirmation.
- Account creation uses the shared account service, normalizes email casing,
  hashes passwords with Argon2id, and records a `user.signed_up` audit event.
- Successful sign-up replaces the anonymous session with an authenticated
  session and redirects to the dashboard.
- The role is assigned as `USER` by the server; submitted role fields are
  ignored. Duplicate-address responses do not disclose whether an account
  already exists.
- No email verification is required in this release.
