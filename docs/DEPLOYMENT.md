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
the published interface and port. The default binds only to loopback. AI26 has
no authentication or role access control, so do not bind it to a public or
untrusted network.

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
Pin image digests and add authentication, TLS, access controls, monitored
off-host backups and tested full-data restoration before exposing sensitive
camera feeds outside a trusted local network.

References: Docker [Compose startup order and health checks](https://docs.docker.com/compose/how-tos/startup-order/),
[Compose production configuration](https://docs.docker.com/compose/how-tos/production/),
and SQLite's [online backup API](https://www.sqlite.org/backup.html) and
[read-only immutable URI mode](https://www.sqlite.org/uri.html).
