"""Offline rotation of the installation key used for analytics pseudonyms."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from auth_key_lock import exclusive_key_maintenance_lock
from key_maintenance import append_audit, backup_database, read_protected_key, verified_audit_head

SCHEMA_VERSION = 12
ACTION = 'privacy_key_rotated'


def rotate(database, active_key_path, new_key_path):
    database = Path(database).resolve(strict=True)
    active_key_path = Path(active_key_path)
    new_key_path = Path(new_key_path)
    old_key = read_protected_key(active_key_path, exact_bytes=None, minimum_bytes=32)
    new_key = read_protected_key(new_key_path, exact_bytes=32)
    active_key_path = active_key_path.resolve(strict=True)
    new_key_path = new_key_path.resolve(strict=True)
    if len({database, active_key_path, new_key_path}) != 3:
        raise ValueError('Database, old key and new key must be separate paths')
    if hmac.compare_digest(old_key, new_key):
        raise ValueError('New privacy key must contain different random bytes')

    old_fingerprint = hashlib.sha256(old_key).hexdigest()
    new_fingerprint = hashlib.sha256(new_key).hexdigest()
    with exclusive_key_maintenance_lock(database):
        connection = sqlite3.connect(str(database), timeout=10, isolation_level=None)
        backup = None
        try:
            connection.execute('PRAGMA busy_timeout=10000')
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version != SCHEMA_VERSION:
                raise RuntimeError(f'Privacy-key rotation requires schema {SCHEMA_VERSION}; database is {version}')
            audit_head = verified_audit_head(connection)
            previous = connection.execute(
                'SELECT data FROM audit WHERE action=? ORDER BY id DESC LIMIT 1', (ACTION,)
            ).fetchone()
            if previous:
                try:
                    expected = json.loads(previous[0])['new_key_sha256']
                except (ValueError, KeyError, TypeError) as error:
                    raise RuntimeError('Previous privacy-key rotation record is invalid') from error
                if not hmac.compare_digest(old_fingerprint, str(expected)):
                    raise RuntimeError('Old privacy key does not match the latest rotation record')

            backup = backup_database(connection, database, label='privacy-key-rotation')
            now = time.time()
            connection.execute('BEGIN IMMEDIATE')
            append_audit(connection, now, ACTION, 'system', {
                'old_key_sha256': old_fingerprint,
                'new_key_sha256': new_fingerprint,
                'analytics_aliases_changed': True,
                'backup_file': backup.name,
            })
            connection.commit()
            return {'old_key_sha256': old_fingerprint, 'new_key_sha256': new_fingerprint,
                    'new_key_file': str(new_key_path), 'database_backup': str(backup),
                    'audit_chain_head_before': audit_head}
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            if backup:
                backup.unlink(missing_ok=True)
            raise
        finally:
            connection.close()


def main(argv=None):
    default_data = Path(os.environ.get('AI26_DATA_ROOT', Path(__file__).parent / 'data'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=default_data / 'ai26.sqlite3')
    parser.add_argument('--old-key', type=Path, default=os.environ.get('AI26_PRIVACY_KEY_FILE'))
    parser.add_argument('--new-key', type=Path, required=True,
                        help='Protected replacement key file containing exactly 32 random bytes')
    args = parser.parse_args(argv)
    if not args.old_key:
        parser.error('set AI26_PRIVACY_KEY_FILE or supply --old-key')
    try:
        result = rotate(args.database, args.old_key, args.new_key)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        print(f'Privacy-key rotation failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    print('Before enabling privacy mode or restarting with privacy enabled, set AI26_PRIVACY_KEY_FILE to new_key_file. Startup verifies its fingerprint. Analytics aliases change; raw observations and reports are not rewritten.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
