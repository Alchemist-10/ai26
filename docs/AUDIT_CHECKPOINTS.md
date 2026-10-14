# Signed audit-chain checkpoints

AI26 stores a locally hash-chained audit log. A signed checkpoint lets an
operator periodically bind the verified chain head to an Ed25519 key and retain
that small record outside the application host. It is useful only when the
checkpoint and trusted public key are actually copied to independent storage.

Generate a key pair once, using storage protected by the host:

```sh
uv run --frozen --directory backend python audit_checkpoint.py generate \
  --private-key /srv/ai26-keys/audit-checkpoint-private.pem \
  --public-key /srv/ai26-keys/audit-checkpoint-public.pem
```

The private key is created with mode `0600`; the command refuses to overwrite
either file. Distribute the public key and its SHA-256 fingerprint through an
independent trusted channel. Keep old public keys for verifying old checkpoints.

Create a checkpoint from a stopped or running SQLite database. The database is
opened read-only and the command refuses to sign an invalid chain. The output
file must not already exist:

```sh
uv run --frozen --directory backend python audit_checkpoint.py create \
  --database /srv/ai26/data/ai26.sqlite3 \
  --private-key /srv/ai26-keys/audit-checkpoint-private.pem \
  --output /mnt/off-host/ai26-audit-2026-10-14.json
```

Copy the checkpoint file to access-controlled, append-only or otherwise
independent storage. To verify a later database against it:

```sh
uv run --frozen --directory backend python audit_checkpoint.py verify \
  --database /srv/ai26/data/ai26.sqlite3 \
  --checkpoint /mnt/off-host/ai26-audit-2026-10-14.json \
  --public-key /srv/ai26-trusted-keys/audit-checkpoint-public.pem
```

Verification checks the checkpoint signature, trusted-key fingerprint, and the
database chain through the signed record. It reports records appended after the
checkpoint. A valid result does not detect deletion or rollback of records that
occurred after the most recent checkpoint, and it does not prove that the source
events were truthful. Checkpoint frequency, off-host retention, key rotation,
revocation, and incident response remain operator responsibilities; this
prototype does not upload checkpoints or manage keys automatically.
