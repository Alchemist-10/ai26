#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
mkdir -p backups
AI26_HOST_UID="$(id -u)"
AI26_HOST_GID="$(id -g)"
export AI26_HOST_UID AI26_HOST_GID
docker compose run --rm backup
