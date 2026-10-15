#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 backups/ai26-full-<timestamp>.tar" >&2
  exit 2
fi
cd "$(dirname "$0")/.."
backup_dir="$(cd backups && pwd -P)"
source_path="$(realpath "$1")"
case "$source_path" in
  "$backup_dir"/*) source_name="${source_path#"$backup_dir"/}" ;;
  *) echo "Choose a full backup stored inside this project's backups/ directory" >&2; exit 2 ;;
esac
AI26_HOST_UID="$(id -u)"
AI26_HOST_GID="$(id -g)"
export AI26_HOST_UID AI26_HOST_GID
was_running=0
restart_backend() {
  if [ "$was_running" -eq 1 ]; then docker compose start backend; fi
}
trap restart_backend EXIT HUP INT TERM
if [ -n "$(docker compose ps --status running -q backend)" ]; then
  was_running=1
  docker compose stop backend
fi
docker compose run --rm restore-full \
  --source "/backups/$source_name" \
  --data-root /app/data \
  --owner-uid "$AI26_HOST_UID" \
  --owner-gid "$AI26_HOST_GID" \
  --confirm-backend-stopped
