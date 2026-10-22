# Rotate the privacy pseudonym key

The privacy key controls analytics pseudonyms. Rotating it changes every valid
plate alias immediately; aliases already seen by users cannot be recalled, and
old and new aliases are not comparable. The procedure leaves raw observations,
evidence reports and their signatures unchanged. Run it offline while the API is
stopped.

## Procedure

1. Stop every Sakshi API process that uses the data directory. Create a new key
   outside the repository and restrict it to the service account:

   ```sh
   umask 077
   openssl rand -out /absolute/path/to/ai26-privacy-next.key 32
   chmod 0400 /absolute/path/to/ai26-privacy-next.key
   ```

   For Compose, make it readable by UID `10001`. Keep the old key unchanged until
   the new key has passed the startup check.

2. Run the rotation tool against the same SQLite database and active key used by
   the stopped service:

   ```sh
   AI26_PRIVACY_KEY_FILE=/absolute/path/to/ai26-privacy.key \
     uv run --frozen --directory backend python rotate_privacy_key.py \
       --database /absolute/path/to/ai26-data/ai26.sqlite3 \
       --new-key /absolute/path/to/ai26-privacy-next.key
   ```

   The database must be at the current schema version and its audit chain must verify. The tool
   refuses a running API or another offline key operation, writes a protected SQLite
   pre-rotation backup, and appends a hash-chained record with old/new key
   fingerprints. It does not rewrite raw plate values or historical reports.

3. Set `AI26_PRIVACY_KEY_FILE` to the new path, then restart with privacy enabled.
   Startup verifies the latest rotation fingerprint and refuses to serve if the
   old or another key is configured. If privacy mode is disabled, startup does
   not require a privacy key; enabling it later still requires the recorded new
   key.

4. Verify the audit chain and confirm that analytics aliases use the new key.
   Keep the database backup according to the protected backup policy. After
   successful verification, retire the old key securely.

This operation rotates only the analytics pseudonym key. It cannot revoke aliases
that were already displayed or copied. It does not rotate MFA, TLS, report-signing
or audit-checkpoint keys.
