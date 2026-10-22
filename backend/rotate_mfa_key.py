"""Offline MFA encryption-key rotation with recovery-code reissue and DB backup."""
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

import mfa
from auth_key_lock import exclusive_rotation_lock
from key_maintenance import append_audit, backup_database, read_protected_key, verified_audit_head


SCHEMA_VERSION = 15


def write_recovery_file(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def recoveries_for(key):
    codes = mfa.new_recovery_codes()
    hashes = [mfa.recovery_hash_with_key(code, key) for code in codes]
    return hashes, codes


def rotate(database, active_key_path, new_key_path, recovery_output):
    database = Path(database).resolve(strict=True)
    active_key_path = Path(active_key_path)
    new_key_path = Path(new_key_path)
    recovery_output = Path(recovery_output).resolve()
    old_key = read_protected_key(active_key_path)
    new_key = read_protected_key(new_key_path)
    active_key_path = active_key_path.resolve(strict=True)
    new_key_path = new_key_path.resolve(strict=True)
    if len({database, active_key_path, new_key_path, recovery_output}) != 4:
        raise ValueError('Database, old key, new key and recovery-code output must be separate paths')
    if hmac.compare_digest(old_key, new_key):
        raise ValueError('New MFA key must contain different random bytes')

    with exclusive_rotation_lock(database):
        connection = sqlite3.connect(str(database), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        backup = None
        codes_path = None
        try:
            connection.execute('PRAGMA busy_timeout=10000')
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version != SCHEMA_VERSION:
                raise RuntimeError(f'MFA rotation requires schema {SCHEMA_VERSION}; database is {version}')
            audit_head = verified_audit_head(connection)
            rows = connection.execute(
                'SELECT username,secret_ciphertext,enabled FROM user_mfa ORDER BY username'
            ).fetchall()
            prepared = []
            one_time_codes = {}
            for row in rows:
                secret = mfa.decrypt_secret_with_key(row['secret_ciphertext'], old_key)
                ciphertext = mfa.encrypt_secret_with_key(secret, new_key)
                hashes, codes = recoveries_for(new_key) if row['enabled'] else ([], [])
                prepared.append((row['username'], row['secret_ciphertext'], row['enabled'], ciphertext, hashes))
                if codes:
                    one_time_codes[row['username']] = codes

            backup = backup_database(connection, database, label='mfa-rotation')
            codes_path = write_recovery_file(recovery_output, {
                'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'purpose': 'One-time MFA recovery codes reissued during encryption-key rotation',
                'users': one_time_codes,
            })
            now = time.time()
            connection.execute('BEGIN IMMEDIATE')
            current_rows = connection.execute(
                'SELECT username,secret_ciphertext,enabled FROM user_mfa ORDER BY username'
            ).fetchall()
            if len(current_rows) != len(prepared) or any(
                    row['username'] != before[0] or bytes(row['secret_ciphertext']) != bytes(before[1])
                    or row['enabled'] != before[2]
                    for row, before in zip(current_rows, prepared)):
                raise RuntimeError('MFA records changed during rotation; no records were changed')
            for username, _old_ciphertext, _enabled, ciphertext, hashes in prepared:
                connection.execute(
                    'UPDATE user_mfa SET secret_ciphertext=?,recovery_hashes=?,updated_at=? WHERE username=?',
                    (ciphertext, json.dumps(hashes, separators=(',', ':')), now, username),
                )
            session_count = connection.execute('SELECT count(*) FROM auth_sessions').fetchone()[0]
            connection.execute('DELETE FROM auth_sessions')
            append_audit(connection, now, 'auth_mfa_key_rotated', 'system', {
                'old_key_sha256': hashlib.sha256(old_key).hexdigest(),
                'new_key_sha256': hashlib.sha256(new_key).hexdigest(),
                'factors_reencrypted': len(prepared),
                'recovery_codes_reissued': sum(len(codes) for codes in one_time_codes.values()),
                'sessions_revoked': session_count,
                'backup_file': backup.name,
                'recovery_file': codes_path.name,
            })
            connection.commit()
            return {
                'factors_reencrypted': len(prepared),
                'enabled_users_reissued': len(one_time_codes),
                'sessions_revoked': session_count,
                'database_backup': str(backup),
                'recovery_codes_file': str(codes_path),
                'new_key_file': str(new_key_path),
                'new_key_sha256': hashlib.sha256(new_key).hexdigest(),
                'audit_chain_head_before': audit_head,
            }
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            if codes_path:
                codes_path.unlink(missing_ok=True)
            if backup:
                backup.unlink(missing_ok=True)
            raise
        finally:
            connection.close()


def main(argv=None):
    default_data = Path(os.environ.get('AI26_DATA_ROOT', Path(__file__).parent / 'data'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=default_data / 'ai26.sqlite3')
    parser.add_argument('--old-key', type=Path, default=os.environ.get('AI26_AUTH_MFA_KEY_FILE'))
    parser.add_argument('--new-key', type=Path, required=True, help='Protected 32-byte replacement key')
    parser.add_argument('--recovery-output', type=Path, required=True, help='New recovery codes file; must not already exist')
    args = parser.parse_args(argv)
    if not args.old_key:
        parser.error('set AI26_AUTH_MFA_KEY_FILE or supply --old-key')
    try:
        result = rotate(args.database, args.old_key, args.new_key, args.recovery_output)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        print(f'MFA key rotation failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    print('Before restarting Sakshi, set AI26_AUTH_MFA_KEY_FILE to the reported new_key_file. Startup verifies the rotated key fingerprint.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
