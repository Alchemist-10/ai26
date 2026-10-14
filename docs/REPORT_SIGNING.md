# Evidence report signatures

Evidence report version 5 includes a detached Ed25519 signature envelope when
`AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE` points to a valid private key. The
signature covers the canonical report payload together with the algorithm, key ID,
and public-key fingerprint before the signature bytes and `package_hash` fields
are added. `package_hash` then covers the complete manifest, including the
signature. The JSON and ZIP exports retain both fields. The print
view displays the signature and fingerprint, but offline verification is performed
on the downloaded JSON manifest.

Generate a key pair outside the repository:

```sh
uv run --frozen --directory backend python report_signing.py generate \
  --private-key /srv/ai26-keys/report-signing-private.pem \
  --public-key /srv/ai26-keys/report-signing-public.pem
```

The command refuses to overwrite either file. It writes an unencrypted PKCS8
private key with mode `0600` and a public key with mode `0644`. Keep the private
key in protected host storage, retain it for the life of reports signed with it,
and provide read access only to the API's UID 10001 when running the container.
The key is not covered by SQLite backups. Distribute the public key and its
printed SHA-256 fingerprint through a channel independent of the report.

To enable signatures in Compose, set `AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE` in
`.env` to the absolute private-key path and run:

```sh
docker compose -f compose.yaml -f compose.evidence-signing.yaml up --build backend frontend
```

The overlay bind-mounts the key read-only. When TLS is also needed, include both
`compose.evidence-signing.yaml` and `compose.tls.yaml`. If the configured key is
missing, too permissive, invalid, or not Ed25519, report creation returns HTTP
503 rather than silently emitting an unsigned report. Without the overlay or key
setting, reports include `signature: null` and retain the unkeyed package digest.

Verify an exported JSON report on an independent machine using a previously
trusted public key:

```sh
uv run --frozen --directory backend python report_signing.py verify \
  --report EVD-0123456789AB.json \
  --public-key /srv/ai26-trusted-keys/report-signing-public.pem
```

Verification checks the package digest, the public-key fingerprint, and the
signature over the canonical report payload. A valid signature proves that those
bytes were signed by the private key corresponding to the trusted public key. It
does not prove the footage is genuine, OCR is accurate, a vehicle identity is
correct, the signer is an authenticated investigator, or the evidence was
continuously held. Maintain trusted public keys across rotation; the current
prototype does not automate key revocation, rotation, remote trust distribution,
or externally checkpointed audit history.

Older report snapshots remain readable and are not retroactively signed. CI and
isolated tests cover signed/unsigned manifests, tampering, key mismatch, private
key permissions, exports and non-overwriting key generation.

The Ed25519 signing and verification calls follow the official
[cryptography 50.0.1 Ed25519 API reference](https://cryptography.io/en/50.0.1/hazmat/primitives/asymmetric/ed25519/).
