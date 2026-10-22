# Signed audit-chain checkpoints

Sakshi stores a locally hash-chained audit log. A signed checkpoint lets an
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

To rotate the checkpoint signer, generate a new pair at new, non-existing paths
with the same `generate` command. Distribute the new public key and fingerprint
through the independent trusted channel, update the scheduled service's private
key path, and create the next checkpoint with the new private key. Keep both
public keys in the trusted set while historical checkpoints signed by either
key remain in scope. Verify a checkpoint during or after the overlap with
repeated `--public-key` arguments:

```sh
uv run --frozen --directory backend python audit_checkpoint.py verify \
  --database /srv/ai26/data/ai26.sqlite3 \
  --checkpoint /mnt/off-host/ai26-audit-2026-10-14.json \
  --public-key /srv/ai26-trusted-keys/audit-checkpoint-old-public.pem \
  --public-key /srv/ai26-trusted-keys/audit-checkpoint-new-public.pem
```

The verifier matches the checkpoint's fingerprint to one supplied trusted key.
Removing a public key from this set revokes local trust for checkpoints signed
by it; this does not rewrite checkpoint files or publish revocation to other
verifiers. Retire the old private key only after the new signer has successfully
created a checkpoint and its verification has been independently checked. Keep
old public keys as long as their checkpoints must remain verifiable.

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
events were truthful. Checkpoint frequency, off-host retention, trusted-key
distribution/revocation, and incident response remain operator responsibilities;
the wrapper does not configure the remote filesystem or manage keys automatically.
The separate offline MFA-key procedure is documented in
[`MFA_KEY_ROTATION.md`](MFA_KEY_ROTATION.md).

## Optional daily Compose/systemd schedule

The repository includes a host wrapper, optional Compose service, and systemd
timer for daily checkpoints. This avoids writing to a local fallback when the
configured checkpoint mount is absent. Choose an independent mounted filesystem
and create an environment file readable by the host service:

```sh
AI26_AUDIT_CHECKPOINT_PRIVATE_KEY_FILE=/srv/ai26-keys/audit-checkpoint-private.pem
AI26_AUDIT_CHECKPOINT_DIR=/mnt/independent-checkpoints/ai26
AI26_AUDIT_CHECKPOINT_MOUNT=/mnt/independent-checkpoints
AI26_AUDIT_CHECKPOINT_UID=10001
AI26_AUDIT_CHECKPOINT_GID=10001
```

The service UID must be able to read the private key and write the mounted
checkpoint directory. Checkpoint files are created without overwriting, with
mode `0600`. The wrapper checks that the mount is active and the destination
resolves beneath its mount root before invoking Compose. This confirms a mounted
destination; it cannot prove the mount is physically off-host or controlled by
a separate administrator. Use storage with the required independence and
retention policy.

Install the sample units after adapting `/opt/ai26` to the checkout path:

```sh
sudo install -d -m 0750 /etc/ai26
sudo install -m 0640 deploy/systemd/audit-checkpoint.env.example /etc/ai26/audit-checkpoint.env
sudoedit /etc/ai26/audit-checkpoint.env
sudo install -m 0644 deploy/systemd/ai26-audit-checkpoint.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/ai26-audit-checkpoint.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai26-audit-checkpoint.timer
sudo systemctl start ai26-audit-checkpoint.service
sudo systemctl status ai26-audit-checkpoint.timer
sudo journalctl -u ai26-audit-checkpoint.service --since today
```

Inspect at least one generated checkpoint and verify it against a database copy
using the earlier `verify` command. Timer activation alone does not prove a
checkpoint succeeded. The timer leaves checkpoints in place; configure retention
on the destination so it preserves the period required by policy.
