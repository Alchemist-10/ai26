# Rotate the MFA encryption key

The MFA key protects enrolled TOTP secrets and recovery-code hashes. Rotate it
only while the API is stopped. The API holds a shared database lock for its
serving lifetime; the rotation command requires an exclusive lock and refuses to
run while any API process owns the database.

## Procedure

1. Stop every Sakshi API process that uses this data directory. Prepare a new
   32-byte random key outside the repository and make it owner-readable only:

   ```sh
   umask 077
   openssl rand -out /absolute/path/to/ai26-auth-mfa-next.key 32
   chmod 0400 /absolute/path/to/ai26-auth-mfa-next.key
   ```

   The key must be readable by the backend UID. Keep the current active key
   available until rotation and restart have both succeeded.

2. Choose a new, protected path for the recovery-code output. It must not
   already exist; the command creates it with mode `0600`. The file contains ten
   new recovery codes for each MFA-enabled user. Arrange secure delivery to each
   user and remove the file after they have stored their codes.

3. Run the command with the same database path and active MFA key used by the
   stopped service:

   ```sh
   AI26_AUTH_MFA_KEY_FILE=/absolute/path/to/ai26-auth-mfa.key \
     uv run --frozen --directory backend python rotate_mfa_key.py \
       --database /absolute/path/to/ai26-data/ai26.sqlite3 \
       --new-key /absolute/path/to/ai26-auth-mfa-next.key \
       --recovery-output /absolute/path/to/secure/ai26-recovery-codes.json
   ```

   The database must be at the current schema version and its audit chain must verify. The tool
   creates a mode-`0600` SQLite backup, re-encrypts every stored MFA secret,
   reissues recovery codes for enabled factors, revokes all sessions, and appends
   a hash-chained audit record with old/new key fingerprints. It never prints
   recovery codes to the terminal.

4. Set `AI26_AUTH_MFA_KEY_FILE` to the new key path in the service environment,
   then start Sakshi. Startup compares the configured key fingerprint with the
   rotation audit record and refuses to serve if the old or another key is still
   configured. Users must sign in again and replace their old recovery codes
   with the contents of the protected output file.

5. Verify the audit chain and a successful MFA login with a user's existing
   authenticator. Retain the database backup according to the deployment's
   protected backup policy. Once that backup is retired and the new setup is
   verified, securely remove the old key and the temporary new-key source copy.

If the API fails to start after rotation, keep it stopped and point
`AI26_AUTH_MFA_KEY_FILE` at the exact new key used by the command. The audit
fingerprint check is intentional: the old key cannot decrypt the rotated
secrets. The backup contains pre-rotation encrypted secrets and must be protected
with the old key for any restore.

This procedure rotates the MFA key only. Privacy pseudonym rotation is documented
in [PRIVACY_KEY_ROTATION.md](PRIVACY_KEY_ROTATION.md). TLS private keys,
report-signing keys and independently retained audit-checkpoint keys have
separate lifecycles.
