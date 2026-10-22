# Sakshi incident response runbook

This runbook covers first response and recovery for the self-hosted Sakshi
prototype. It does not provide automated incident detection, paging, external
notification, forensic acquisition, or a substitute for the deploying
organization's incident policy. The default Compose stack has authentication
disabled; do not treat its local audit records as proof of who accessed it.

## First response

1. Assign an incident lead and record an incident ID, UTC start time, affected
   deployment, reporter, suspected scope, and the actions taken. Keep credentials,
   recovery codes, raw plates, and evidence images out of ordinary tickets/chat.
2. Contain active exposure at the network boundary. Restrict access to the host
   or stop the exposed frontend/TLS service if necessary. For Compose, inspect the
   actual project first with `docker compose ps`; stop only the service that is
   publishing the affected listener. A backend stop interrupts capture and
   processing, so record that operational impact.
3. Preserve the current state before rotating keys, restoring a database, pruning
   media, or recreating containers. Record `date -u --iso-8601=seconds`, the
   deployed commit/image, `docker compose ps`, and the affected time range. Save
   bounded service logs to access-controlled incident storage, for example:

   ```sh
   docker compose logs --timestamps --since 2026-10-15T00:00:00Z backend frontend frontend_tls
   ```

   Omit service names not present in that deployment. Review logs before sharing;
   never attach `.env`, key files, passwords, RTSP URLs, recovery codes, database
   files, or unredacted evidence to a public issue.
4. Create a protected database snapshot using `./scripts/backup.sh`, or stop the
   backend and use `./scripts/backup-full.sh` to capture SQLite plus managed
   source releases, upload receipts, cached models, and read-artifact images.
   Full archives are unencrypted and must be stored on access-controlled,
   encrypted backup storage. Neither procedure includes externally mounted
   footage, custom model mounts, or host secrets.
5. Avoid destructive cleanup or speculative repair. Keep the original database,
   affected source files, reports, logs, and any off-host checkpoints unchanged.
   Record hashes and copies through the approved evidence-handling procedure.

## Triage and containment

| Signal | Immediate checks and containment |
| --- | --- |
| Suspected account/session compromise | Restrict ingress if exposure is active. In authenticated mode, an administrator can disable the account or perform a reason-recorded password reset in User administration; role/status and password changes revoke sessions. Deliver temporary passwords through an approved out-of-band channel. A self-service password change also revokes sessions. The reset reason does not independently verify identity; the default stack has no external identity provider. |
| MFA encryption key lost or exposed | Stop every API using the database. Preserve the current key and database securely, then follow [MFA key rotation](MFA_KEY_ROTATION.md). Rotation revokes sessions and reissues recovery codes; protect the recovery output and deliver it only through the approved private channel. |
| Privacy pseudonym key lost or exposed | Restrict analytics access and assess which aliases were exposed. Follow [privacy-key rotation](PRIVACY_KEY_ROTATION.md); rotation changes aliases and cannot recall previously viewed/copied aliases. Raw observations and signed reports are not rewritten. |
| Report-signing private key suspected compromised | Stop using that key for new reports. Generate and deploy a new pair using [report-signing key rotation](REPORT_SIGNING.md); distribute the new public-key fingerprint independently, preserve old public keys for historical verification, and document the suspected exposure period. A valid signature does not prove source authenticity. |
| Audit-checkpoint key or checkpoint destination compromised | Preserve existing checkpoints and public keys. Rotate the signer as described in [signed audit checkpoints](AUDIT_CHECKPOINTS.md). Check that the configured independent mount is present before creating another checkpoint; the schedule does not itself prove off-host custody or send an alert. |
| TLS certificate/private key compromised or expired | Stop the `frontend_tls` listener if it is exposed, replace the certificate/key through the deployment's certificate authority process, then recreate the TLS service and verify the HTTPS listener. Sakshi does not renew certificates automatically. Keep the private key outside routine database backups. |
| Audit integrity check fails | Preserve the database and latest trusted checkpoints. In authenticated mode, an administrator can inspect `GET /api/audit/integrity`; do not edit or truncate audit rows to make the result pass. Verify the database against each independently retained checkpoint with its trusted public key and record the exact verification output. A valid checkpoint only protects history through its signed record. |
| Database corruption or accidental data loss | Preserve the current database and WAL/SHM files before any restore. Run `./scripts/backup.sh` if the service can still produce a consistent snapshot. Restore only with the backend stopped, using the explicit confirmation workflow in [deployment and backups](DEPLOYMENT.md). Verify integrity, audit chain, users, and application health before reopening access. |
| Source media missing, changed, or selected incorrectly | Do not run source cleanup. Preserve `active.json`, release manifests, and both original/playback files. Camera settings reports missing/size-changed files; startup verifies managed-file hashes. Follow [source selection and rollback](SOURCE_SELECTION.md) or [source import recovery](SOURCE_IMPORT.md) with the app stopped where required. A full data-volume backup restores managed source releases; external footage and host-mounted files must be recovered separately. |
| Suspected exposure of plates, faces, or report contents | Restrict the affected listener and accounts, preserve relevant access/audit records, and identify whether evidence JSON, ZIP, print, image, or video endpoints were available. Privacy display mode masks detected regions in sampled views only; reports and source files retain original data. The configured rules do not send notifications. |

## Recovery checks

Before restoring access, record and verify the recovery steps that apply:

- Confirm the selected deployment configuration and secrets are the intended ones;
  do not copy secrets into command history or incident notes.
- Confirm the API health endpoint responds and reports the expected schema. If a
  source change was involved, refresh source status and verify both inference and
  playback roles after restart.
- In authenticated mode, verify administrator sign-in, role restrictions, case
  scope, and MFA where enabled. Confirm affected sessions were revoked.
- Run the authenticated audit-integrity check and verify the database against the
  latest independent checkpoint when one exists. Record the checkpoint time and
  how much later history it cannot protect.
- Verify any restored SQLite snapshot with the repository's restore command and
  integrity check. For a full data-volume restore, verify the SHA-256 manifest,
  source status, representative artifact downloads, and report integrity. Recover
  external footage and custom model mounts separately.
- For signed evidence, verify representative reports offline using the trusted
  public key(s) and record any key overlap/revocation decisions.
- Re-enable only the listener and users needed for service, then observe source,
  processing, and error metrics. Monitoring rules are local Prometheus rules and
  do not notify responders without an external Alertmanager configuration.

## Closeout record

Keep a restricted incident record with the timeline, affected systems/data,
containment and recovery actions, snapshot/checkpoint identifiers, verification
outputs, key fingerprints (never key contents), unresolved exposure window, and
follow-up owners. Record which conclusions are verified and which remain
uncertain. Preserve original artifacts according to the organization's retention
and evidence-handling rules; Sakshi does not supply those external policies.

## Related procedures and limits

- [Deployment, backup and restore](DEPLOYMENT.md)
- [Authentication and access scope](AUTHENTICATION.md)
- [MFA key rotation](MFA_KEY_ROTATION.md)
- [Privacy key rotation](PRIVACY_KEY_ROTATION.md)
- [Evidence report signatures](REPORT_SIGNING.md)
- [Signed audit-chain checkpoints](AUDIT_CHECKPOINTS.md)
- [TLS deployment](DEPLOYMENT.md#optional-tls-reverse-proxy)
- [Source selection and rollback](SOURCE_SELECTION.md)
- [Source import and cleanup](SOURCE_IMPORT.md)

Sakshi currently has no automated TLS lifecycle, external alert delivery, complete
off-host media backup workflow, automatic incident-response workflow, or
independently managed case registry. Key-compromise, TLS, media-restoration and
off-host procedures still need deployment-specific exercises before relying on
them during an incident.

The database-only stop/backup/mutate/restore/restart path was exercised with an
isolated temporary API on 2026-10-15. Its health check passed, the backup had mode
`0600` and passed SQLite integrity checking, the post-backup test change was
removed by restore, and the restored audit chain verified. The record is in
[`validation/incident-backup-restore-drill-2026-10-15.json`](validation/incident-backup-restore-drill-2026-10-15.json).
The isolated managed-data drill additionally restored database state, source
manifests, upload receipts, cached model files and image artifacts from a
manifest-verified archive; a tampered member was rejected without replacing the
current data. It did not restore externally mounted footage, custom model mounts
or host secrets, and did not exercise auth, TLS, key compromise or off-host
storage.
