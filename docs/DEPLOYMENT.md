# Local Compose deployment and database backups

AI26 can run as one inference/API container and one production-built Nginx
frontend. Nginx serves the static React build and proxies `/api/` to the backend
over Compose's private network. Hashed frontend assets use gzip compression and
immutable cache headers. Only the frontend port is published, bound to
`127.0.0.1:5174` by default. The backend uses one Uvicorn worker because its
processor and SQLite state are process-local. The data volume keeps SQLite,
managed source releases, model cache and read-artifact files across container
recreation. Put original footage under `backend/data/footage` before startup, or
set `AI26_FOOTAGE_DIR` to its host directory.

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

For a quick configuration check use `docker compose config -q`. To stop the
stack use `docker compose down`; named application data remains. `docker compose
down -v` removes that persistent data volume.

This is a self-hosted packaging baseline, not a hardened public deployment.
Authentication and role checks are available as an opt-in overlay; off-host
backups, tested full-data restoration, external audit checkpoints and case-level
authorization remain deployment work. The optional TLS overlay below provides
transport encryption only.

The backend exposes Prometheus text metrics at `/api/metrics`. It reports bounded
per-camera health and recent processor timing summaries without event, plate, or
person data. When the authentication overlay is enabled, only administrator
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
group to the AI26 host operator, and do not expose the Prometheus UI outside a
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

References: Docker [Compose startup order and health checks](https://docs.docker.com/compose/how-tos/startup-order/),
[Compose production configuration](https://docs.docker.com/compose/how-tos/production/),
[Compose profiles](https://docs.docker.com/compose/how-tos/profiles/), Prometheus
[scrape and authorization configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/),
and SQLite's [online backup API](https://www.sqlite.org/backup.html) and
[read-only immutable URI mode](https://www.sqlite.org/uri.html).
