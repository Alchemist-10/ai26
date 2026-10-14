# Authentication and access scope

Authentication is opt-in so the local development workflow remains available.
For a deployed instance, create a long random administrator passphrase in a file
outside the repository and make it readable by the backend container's UID
10001. The file must contain at least 14 characters. Keep it protected with
owner-only access and remove it after the first account has been created.

```sh
install -m 0400 /dev/null /absolute/path/to/ai26-admin-bootstrap-password
sudo chown 10001:10001 /absolute/path/to/ai26-admin-bootstrap-password
```

Write the passphrase into that file using a password manager or another secure
method. The source file's owner must be UID 10001 (or use a protected group
readable by UID 10001), because the backend does not run as root. Do not commit
the secret or put it in `.env`.

Run HTTP-only local authentication with:

```sh
AI26_ADMIN_BOOTSTRAP_PASSWORD_FILE=/absolute/path/to/ai26-admin-bootstrap-password \
  docker compose -f compose.yaml -f compose.auth.yaml up --build backend frontend
```

For TLS, combine the overlays and enable secure cookies:

```sh
AI26_ADMIN_BOOTSTRAP_PASSWORD_FILE=/absolute/path/to/ai26-admin-bootstrap-password \
AI26_TLS_CERT_FILE=/absolute/path/to/fullchain.pem \
AI26_TLS_KEY_FILE=/absolute/path/to/private-key.pem \
AI26_AUTH_COOKIE_SECURE=1 \
  docker compose -f compose.yaml -f compose.tls.yaml -f compose.auth.yaml up --build backend frontend_tls
```

On first startup, the backend creates the configured administrator account
once. It never resets that account's password from the bootstrap file. Later
starts do not need to read the file, but Compose keeps the bind mount configured;
retain the file or remove the auth overlay only after planning a replacement
bootstrap procedure. User records, hashed passwords, sessions, and login-failure
limits are stored in SQLite. Passwords use PBKDF2-HMAC-SHA256 with 600,000
iterations; session tokens are random, stored only as hashes, expire after eight
hours, and are revoked on password, role, or disabled-state changes. Login
failures are limited by client address to ten attempts per 15 minutes.

The cookie is `HttpOnly`, `SameSite=Strict`, scoped to `/api`, and marked Secure
when `AI26_AUTH_COOKIE_SECURE=1`. Mutating API requests require the per-session
CSRF header. TLS is required when the service is reachable beyond a trusted
localhost environment. The bundled TLS proxy replaces `X-Real-IP` before the
backend uses it for rate limiting.

Roles are hierarchical: administrators can manage accounts and inspect audit
integrity; operators inherit analyst/viewer reads and can edit camera settings,
sources, alert reviews, and rules; analysts can inspect scoped event, alert,
analytics, query, and evidence data; viewers can list cameras only. Unknown API
routes are administrator-only while authentication is enabled.

Sensitive endpoints require a case ID and one of `investigation`,
`traffic_analysis`, `incident_response`, or `system_test`. The UI sends this
context with each request; native video/image requests pass it in the URL query.
The backend validates it and appends a hash-chained `sensitive_access` audit
entry before serving the request. Repeated GET polls for the same user, case,
purpose and route are coalesced into one audit entry per minute to keep live
previews from growing the audit chain on every poll; mutations are recorded each
time. This is an access record, not an authorization system for specific cases:
any role permitted to read the endpoint may choose a syntactically valid case ID.
Case-level grants,
account recovery, password self-service, external identity providers, and
multi-factor authentication remain unimplemented.

The initial UI supports sign-in, session restoration, case/purpose selection,
and sign-out. Administrators can manage users through the protected
`/api/auth/users` endpoints; a dedicated account-management screen remains
pending.
