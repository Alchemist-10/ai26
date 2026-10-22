# Local Compose deployment and database backups

Sakshi can run as one inference/API container and one production-built Nginx
frontend. Nginx serves the static React build and proxies `/api/` to the backend
over Compose's private network. Hashed frontend assets use gzip compression and
immutable cache headers. Only the frontend port is published, bound to
`127.0.0.1:5174` by default. The backend uses one Uvicorn worker because its
processor and SQLite state are process-local. The data volume keeps SQLite,
managed source releases, model cache and read-artifact files across container
recreation. Put original footage under `backend/data/footage` before startup, or
set `AI26_FOOTAGE_DIR` to its host directory.

Sampled observations and evidence images expire after seven days by default.
Set `AI26_OBSERVATION_RETENTION_DAYS` to an integer from 7 to 365 to retain them
longer. The API rejects values outside that range at startup. Report leases can
extend referenced image retention until a report's independent 24-hour expiry;
original managed video releases and model files have separate storage lifecycles.

Start the local stack with:

```sh
docker compose up --build
```

Open <http://127.0.0.1:5174>. Set `AI26_PROCESSING_ENABLED=0` in the shell or
`.env` file for a UI/API-only run. `AI26_HOST` and `AI26_FRONTEND_PORT` can change
the published interface and port. The default binds only to loopback. This base
stack has authentication disabled; add the [authentication overlay](AUTHENTICATION.md)
before sharing the UI, and use it with TLS outside a trusted local machine.

Create a consistent SQLite snapshot without stopping the service with:

```sh
./scripts/backup.sh
```

This uses SQLite's online backup API, verifies `PRAGMA integrity_check`, writes
to a temporary file before publication, and keeps the newest 30 snapshots in
`backups/`. Set `AI26_BACKUP_KEEP` to change retention. The one-shot backup
container has volume access needed for SQLite live-WAL locks, then assigns the
private snapshot to your host user; the API itself stays non-root. The backup
contains the database only; it does not contain footage, model weights, managed source files,
or JPEG evidence artifacts. Keep a separate protected backup of those files if
you need complete report/source recovery. Restore only while the backend is
stopped, preserve the old database first, and remove any stale `-wal`/`-shm`
sidecars before restarting:

```sh
docker compose stop backend
docker compose run --rm restore --source /backups/ai26-YYYYMMDDTHHMMSS.ffffffZ.sqlite3 --confirm-backend-stopped --owner-uid 10001 --owner-gid 10001
docker compose start backend
```

For a consistent backup of the database plus AI26-managed media, use:

```sh
./scripts/backup-full.sh
```

This stops the backend if it was running, snapshots SQLite, packages the
`artifacts/`, `sources/`, `uploads/`, and `models/` directories with a
SHA-256/size manifest, restricts the archive to mode `0600`, rotates old full
snapshots using `AI26_BACKUP_KEEP`, and restarts the backend on exit. A full
archive is an unencrypted `.tar` file; store it on encrypted, access-controlled
backup storage. It excludes the externally mounted original-footage directory,
custom model files mounted from `./models`, TLS/authentication secrets, and
anything outside `/app/data`.

To restore one full archive, keep it under `backups/` and run:

```sh
./scripts/restore-full.sh backups/ai26-full-YYYYMMDDTHHMMSS.ffffffZ.tar
```

The script stops a running backend, verifies every manifest digest and the
restored database before replacing managed data, assigns files to the invoking
host user, and restarts the backend if it stopped it. On validation or install
failure, the current managed paths are restored. A successful restore replaces
the database and managed directories; take a fresh full backup first if the
current state must remain recoverable. The destination data volume needs enough
free space to stage the incoming managed files alongside current content.

For a quick configuration check use `docker compose config -q`. To stop the
stack use `docker compose down`; named application data remains. `docker compose
down -v` removes that persistent data volume.

This is a self-hosted packaging baseline, not a hardened public deployment.
Authentication and role checks are available as an opt-in overlay; off-host
backup custody, original-footage/custom-model restoration, independent
audit-checkpoint custody and a deployment-specific case registry remain
deployment work. Database-only and AI26-managed-data restore paths have isolated
integration drills; neither captures files mounted outside `/app/data`.
The optional TLS overlay below provides
transport encryption only.

## Linux systemd deployment

For a host-managed Linux process, `deploy/systemd/ai26.service.example` runs the
repository launcher as the dedicated `ai26` service account. Create that system
account, deploy the checkout at `/opt/ai26`, and prepare persistent paths before
enabling the service. The launcher rebuilds the optimized frontend during
startup, so the service account needs write access to the checkout/build output.
Run `useradd` only when the service account does not already exist:

```sh
sudo useradd --system --create-home --home-dir /var/lib/ai26 --shell /usr/sbin/nologin ai26
sudo install -d -o ai26 -g ai26 /var/lib/ai26 /var/lib/ai26/sources
sudo chown -R ai26:ai26 /opt/ai26
sudo -u ai26 -H sh -c 'cd /opt/ai26/backend && uv sync --frozen'
sudo -u ai26 -H npm ci --prefix /opt/ai26/frontend
sudo install -d -o root -g root -m 0755 /etc/ai26
```

Create `/etc/ai26/ai26.env` with the same deployment-specific settings used by
the app. At minimum, point `AI26_DATA_ROOT` to `/var/lib/ai26` and
`AI26_SOURCE_ROOT` to `/var/lib/ai26/sources`; add `AI26_FOOTAGE_DIR` if the
recordings are stored elsewhere. Keep that file root-owned and mode `0600`, and
grant the service account read access to footage and write access to managed
data. Never put RTSP passwords in command-line arguments.

Install and start the example unit:

```sh
sudo install -o root -g root -m 0644 /opt/ai26/deploy/systemd/ai26.service.example /etc/systemd/system/ai26.service
sudo systemctl daemon-reload
sudo systemctl enable --now ai26.service
sudo systemctl status ai26.service
sudo journalctl -u ai26.service -n 100 --no-pager
curl -fsS http://127.0.0.1:8001/healthz
curl -fsS http://127.0.0.1:5174/ -o /dev/null
```

The unit uses `run.py` so systemd starts and stops the API and optimized
frontend together; the launcher handles graceful shutdown of both child process
groups. After selecting replacement footage or changing restart-bound model or
camera settings, activate them and verify health with:

```sh
sudo systemctl restart ai26.service
curl -fsS http://127.0.0.1:8001/healthz
```

`/healthz` is a minimal liveness response. Detailed per-camera state at
`/api/health` requires an administrator session whenever authentication is
enabled; use the authenticated dashboard or a protected local profile cookie.

Use `sudo systemctl stop ai26.service` for planned maintenance and
`sudo journalctl -fu ai26.service` to follow startup/recovery logs. The template
assumes the checkout, `uv`, Node.js/npm and configured footage paths exist on the
host. It does not configure a public reverse proxy, TLS, firewall, external
identity provider, or camera/NVR credentials; configure those separately before
allowing remote access.

The backend exposes Prometheus text metrics at `/api/metrics`. It reports bounded
per-camera health, recent processor timing summaries, and managed evidence-image
storage use/capacity without event, plate, or person data. The starter alert rules
warn when evidence-image storage stays at or above 90% for two minutes. When the authentication overlay is enabled, only administrator
sessions can scrape this endpoint. For unattended scraping, set
`AI26_METRICS_TOKEN_FILE` to a protected file containing at least 32 random
ASCII characters; a matching bearer token then grants access to this route only.
For example, generate a 64-character hexadecimal secret with
`openssl rand -hex 32`. The token file is read on each scrape so it can be
rotated without restarting the API. Keep the token out of environment values,
source control and request logs, and mount it read-only into the API and scraper.
With authentication disabled, the route follows the local stack's
unauthenticated API policy. Configure the scraper to reach the backend on the
private Compose network or through a trusted proxy. The optional monitoring
overlay below supplies a local Prometheus service and starter alert rules;
external notification delivery still requires Alertmanager configuration.

An optional RTSP path accepts a private JSON map from existing camera IDs to
`rtsp://` or `rtsps://` URLs. Create a host-side file such as
`{"CAM-01":"rtsp://user:password@camera.local:554/stream"}`, restrict it with
`chmod 600` and make it owned by container UID 10001 (for example,
`sudo chown 10001:10001 /path/to/ai26-live-sources.json`), set
`AI26_LIVE_SOURCES_FILE` in `.env`, and start Compose with the overlay:

```sh
docker compose -f compose.yaml -f compose.rtsp.yaml up --build
```

The API validates the file permissions and camera IDs at startup. One reader
thread per configured camera has five-second open and three-second read
timeouts, a latest-frame-only buffer, five-second freshness limit, reconnect
backoff and no URL exposure in health/API responses or capture logs. Inference,
event storage and browser previews use the same pipeline as recorded input;
`/api/video/{camera_id}` remains unavailable for live cameras. Live timestamps
are host arrival times and are labeled `capture_arrival_clock`; no camera/NVR
clock synchronization is claimed. Cross-camera live routes using these arrival
times remain unresolved candidates with null physical speed until clock offsets
and buffering delays are calibrated. Use RTSP over a trusted camera network (or
RTSPS where supported) and rotate credentials at the camera. ONVIF discovery,
camera clock synchronization, live failover testing on actual hardware and
credential lifecycle management remain open work. An administrator can use
Camera settings → **Discover ONVIF cameras** to send a bounded two-second
WS-Discovery probe to the local network. The API returns device service
addresses and scopes. The **Read camera profiles** action can then make bounded
read-only `GetCapabilities`, `GetProfiles` and `GetStreamUri` requests using
operator-entered ONVIF UsernameToken PasswordDigest credentials. The credentials
are sent to the Sakshi API and then to the discovered camera, are not persisted,
and are cleared from the form after the request. Redirects and environment
proxies are disabled, and endpoint and returned stream hosts must match the
discovered private IPv4 address. Returned URLs with credentials, query strings,
fragments, public addresses or a different host are withheld. The action also
performs a read-only `GetSystemDateAndTime` request and displays a camera-to-host
clock offset estimate with network and one-second timestamp-resolution
uncertainty; it does not set the camera clock. The ONVIF Core specification
defines this operation as read-only and returns UTC date/time, daylight-saving,
and time-source information ([official specification](https://www.onvif.org/specs/core/ONVIF-Core-Spec-v2412.pdf)).
The estimate is relative to the Sakshi host clock, whose own UTC accuracy is not
assessed, so it is diagnostic and not a calibration claim. This inspection does
not activate a stream or change source mappings; a reviewed RTSP/RTSPS URL
must still be placed in the protected host-side source file. ONVIF digest-auth
compatibility varies by vendor, so test this flow on each supported camera/NVR
model before relying on it. Discovery needs host/network support for IPv4
multicast on UDP 3702; camera interoperability, clock synchronization and live
failover on hardware remain open work. Both ONVIF endpoints are administrator-only
when authentication is enabled and are recorded in the sensitive-access audit
log.

For a local Prometheus instance and starter alert rules, create a token file and
grant the backend and Prometheus containers read access through a shared host
group. For example:

```sh
mkdir -p secrets
openssl rand -hex 32 > secrets/ai26-metrics-token
chmod 0440 secrets/ai26-metrics-token
export AI26_METRICS_TOKEN_FILE="$PWD/secrets/ai26-metrics-token"
export AI26_METRICS_FILE_GID="$(stat -c '%g' "$AI26_METRICS_TOKEN_FILE")"
docker compose -f compose.yaml -f compose.monitoring.yaml --profile monitoring up --build
```

The Prometheus UI binds to `127.0.0.1:9090` by default. Restrict the token file's
group to the Sakshi host operator, and do not expose the Prometheus UI outside a
trusted machine without adding access control and TLS. The included rules surface
API scrape failure, total source loss, stale processed frames and repeated camera
processing failures. They do not send notifications; configure Alertmanager if
delivery is required. The monitoring overlay retains seven days of local samples.
Run the deterministic alert firing/recovery checks with the same pinned image:

```sh
docker run --rm --entrypoint=/bin/promtool \
  --mount "type=bind,src=$PWD/ops,dst=/ops,readonly" \
  prom/prometheus:v3.15.0 test rules /ops/ai26-alert-tests.yml
```

## Optional TLS reverse proxy

For an HTTPS endpoint with an existing certificate, set `AI26_TLS_CERT_FILE` and
`AI26_TLS_KEY_FILE` to absolute host paths outside the repository, then run:

```sh
docker compose -f compose.yaml -f compose.tls.yaml up --build backend frontend_tls
```

The TLS service publishes the UI on `127.0.0.1:8443` by default and redirects its
HTTP port (`8080`) to HTTPS. Set `AI26_TLS_HOST` to a LAN interface only when the
host firewall and access policy are ready; set `AI26_TLS_PORT` and
`AI26_HTTP_REDIRECT_PORT` if those host ports are occupied. Mount the full-chain
certificate and private key read-only. Keep the private key owned by the host
operator with mode `0600`, outside source control and outside routine database
backups. `.gitignore` excludes the local `secrets/` directory and `*.key`/`*.pem`
files.
Renew the certificate on the host and recreate/reload the TLS service after
renewal. The proxy accepts TLS 1.2/1.3 and sends HSTS on HTTPS responses.

This overlay adds transport encryption only. Combine it with the authentication
overlay and set `AI26_AUTH_COOKIE_SECURE=1` before using the TLS listener for
authenticated access. The TLS listener alone does not authenticate users or
authorize roles, and authentication does not create an externally trusted audit
checkpoint. Do not publish either listener to an untrusted network without a
deployment review.

For public-domain HTTPS with automatic certificate issuance, renewal, and HTTP
redirects, use the optional Caddy overlay instead:

```sh
AI26_DOMAIN=ai26.example.org \
AI26_ADMIN_BOOTSTRAP_PASSWORD_FILE=/absolute/path/to/ai26-admin-password \
docker compose -f compose.yaml -f compose.caddy.yaml up --build -d
```

The overlay enables Sakshi authentication with Secure cookies and requires the
bootstrap password file. Before starting, point the domain's DNS A/AAAA records
to the host and allow inbound TCP 80/443 (UDP 443 is optional for HTTP/3).
`AI26_CADDY_HOST` defaults to `0.0.0.0` for public certificate challenges; set
it to a specific interface if your network policy requires that. Caddy proxies
the existing production frontend, which continues to route `/api/` internally,
and stores its certificate state in persistent `caddy_data`/`caddy_config`
volumes. Keep those volumes persistent; include them in protected deployment
backups if you need their current certificate keys and account state. Caddy
automatically manages certificate renewals and HTTP-to-HTTPS redirects when the
hostname, network and persistent-storage prerequisites are met. This flow is
packaged and configuration-validated locally; public issuance and renewal still
need a real domain and reachable deployment to verify.

The Caddy overlay requires its own `.env` entries rather than certificate file
paths. It does not alter the base local launcher or the manual-certificate TLS
overlay. See Caddy's [automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https),
[HTTPS quick-start](https://caddyserver.com/docs/quick-starts/https), and
[Docker Compose setup](https://caddyserver.com/docs/running#docker-compose).

References: Docker [Compose startup order and health checks](https://docs.docker.com/compose/how-tos/startup-order/),
[Compose production configuration](https://docs.docker.com/compose/how-tos/production/),
[Compose profiles](https://docs.docker.com/compose/how-tos/profiles/), Prometheus
[scrape and authorization configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/),
and SQLite's [online backup API](https://www.sqlite.org/backup.html) and
[read-only immutable URI mode](https://www.sqlite.org/uri.html).
