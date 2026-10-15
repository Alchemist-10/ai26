#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
mkdir -p backups
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
docker compose run --rm backup-full
