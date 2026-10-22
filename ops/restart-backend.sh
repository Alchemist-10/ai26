#!/usr/bin/env bash
set -euo pipefail

# Restart only the API service so it reloads selected source bindings, then
# wait for the container's local health endpoint before reporting success.
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required to restart the Sakshi backend." >&2
  exit 2
fi
if ! docker compose config --services | awk '$0 == "backend" { found=1 } END { exit !found }'; then
  echo "The current Compose project has no backend service. Run this from the Sakshi deployment directory." >&2
  exit 2
fi
if [[ -z "$(docker compose ps -q backend)" ]]; then
  echo "The Sakshi Compose backend is not running; start the deployment before activating a source." >&2
  exit 2
fi

echo "Restarting the Sakshi backend to activate selected camera sources…"
docker compose restart backend

deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  if docker compose exec -T backend python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8001/healthz", timeout=3)' \
    >/dev/null 2>&1; then
    echo "AI26 backend health check passed. Refresh source status in Camera settings."
    exit 0
  fi
  sleep 2
done

echo "AI26 backend did not become healthy within 90 seconds. Inspect: docker compose logs --tail=100 backend" >&2
exit 1
