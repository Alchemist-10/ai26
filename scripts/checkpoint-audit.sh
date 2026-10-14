#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${AI26_AUDIT_CHECKPOINT_PRIVATE_KEY_FILE:?Set the protected audit-checkpoint private-key path}"
: "${AI26_AUDIT_CHECKPOINT_DIR:?Set the mounted checkpoint output directory}"
: "${AI26_AUDIT_CHECKPOINT_MOUNT:?Set the mounted checkpoint filesystem root}"

if [ ! -f "$AI26_AUDIT_CHECKPOINT_PRIVATE_KEY_FILE" ]; then
  echo "Audit checkpoint private key is unavailable" >&2
  exit 2
fi
case "$AI26_AUDIT_CHECKPOINT_MOUNT" in /*) ;; *) echo "Checkpoint mount path must be absolute" >&2; exit 2 ;; esac
case "$AI26_AUDIT_CHECKPOINT_DIR" in /*) ;; *) echo "Checkpoint output directory must be absolute" >&2; exit 2 ;; esac
if ! mountpoint -q -- "$AI26_AUDIT_CHECKPOINT_MOUNT"; then
  echo "Audit checkpoint filesystem is not mounted; refusing local fallback" >&2
  exit 2
fi
mkdir -p -- "$AI26_AUDIT_CHECKPOINT_DIR"
mount_root=$(realpath -e -- "$AI26_AUDIT_CHECKPOINT_MOUNT")
checkpoint_dir=$(realpath -e -- "$AI26_AUDIT_CHECKPOINT_DIR")
case "$checkpoint_dir/" in
  "$mount_root/"|"$mount_root/"*) ;;
  *) echo "Checkpoint output directory must be inside the mounted checkpoint filesystem" >&2; exit 2 ;;
esac

stamp=$(date -u +%Y%m%dT%H%M%SZ)
output="/checkpoints/ai26-audit-${stamp}.json"
cd "$repo_root"
docker compose --profile audit-checkpoint \
  -f compose.yaml -f compose.audit-checkpoints.yaml \
  run --rm audit-checkpoint create \
  --database /app/data/ai26.sqlite3 \
  --private-key /run/secrets/audit-checkpoint-private.pem \
  --output "$output"
