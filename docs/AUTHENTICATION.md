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
bootstrap procedure. User records, per-case grants, hashed passwords, sessions, and login-failure
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
time. Administrators can assign one or more case IDs to each non-admin account;
those users can only select and access the cases assigned to them. Administrators
retain oversight across all case IDs. Purpose is logged for accountability but is
not a separate role permission. There is no shared case registry, transfer or
delegation workflow, or built-in mechanism to establish that an entered case ID
corresponds to an external case-management system. Signed-in users can change
their password after confirming the current one; the change revokes all sessions
and requires a fresh sign-in. MFA-enrolled users can recover a forgotten password
from the sign-in screen using a current authenticator code or an unused MFA
recovery code. Recovery revokes all existing sessions, consumes recovery codes
once, and shares an atomic per-address attempt limit with sign-in. The
public endpoint returns the same response for unknown, disabled, non-MFA and
success cases to avoid disclosing account state. Accounts without MFA still need
an administrator to reset their password; help-desk recovery and external
identity providers are not implemented.

The initial UI supports sign-in, session restoration, case/purpose selection,
and sign-out. Signed-in users can change their password in Account security.
The sign-in screen also offers MFA-backed password recovery when the protected
MFA key is configured.
Administrators can manage users, case grants, roles, account status, and password
resets through the protected account-management screen.

Active alert escalations are stored with the case selected when they are
created. Non-admin users can list and resolve only escalations in that case;
administrators can review the full queue. This does not provide general
row-level case isolation for alerts, observations or evidence, and legacy
unscoped escalations remain administrator-managed.

## Authenticator MFA

MFA is an optional extension to the auth overlay. Create a separate 32-byte key,
keep it outside the repository, and make it readable only by the backend UID:

```sh
umask 077
openssl rand -out /absolute/path/to/ai26-auth-mfa.key 32
sudo chown 10001:10001 /absolute/path/to/ai26-auth-mfa.key
chmod 0400 /absolute/path/to/ai26-auth-mfa.key
```

Start auth with MFA support by combining `compose.auth.yaml` and
`compose.auth-mfa.yaml` and setting `AI26_AUTH_MFA_KEY_FILE`. MFA secrets are
AES-GCM encrypted in schema 13; the database stores the last accepted TOTP
time-step so each authenticator code can be used only once. Counter updates are
transactional, so simultaneous requests presenting the same code create at most
one authenticated session. The key file must be protected and backed up securely.
If the key is lost, stored TOTP secrets cannot be decrypted.
For the offline rotation procedure, including recovery-code reissue and the
startup key-fingerprint check, see [MFA key rotation](MFA_KEY_ROTATION.md).

Signed-in users can open Account security, enroll a standards-based six-digit
TOTP authenticator, and confirm enrollment before MFA is enabled. Ten one-use
recovery codes are shown once at enrollment and stored only as keyed hashes.
Login requires a TOTP or unused recovery code for enrolled accounts. Users can
disable MFA only after re-entering their password and a current TOTP code.
Administrators can reset a user's MFA from User administration; this disables
the factor and revokes that user's sessions. The reset is audited. There is no
self-service email/phone recovery. Keep the MFA key available and protected:
without it, TOTP cannot be checked and recovery-code hashes cannot be verified.
Users who lose both their authenticator and every recovery code need an
administrator to reset MFA and their password.
