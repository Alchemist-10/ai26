"""Shared offline key-maintenance primitives for protected local secrets."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def verified_audit_head(connection):
    rows = connection.execute(
        'SELECT id,ts,action,subject,data,previous_hash,record_hash FROM audit ORDER BY id'
    ).fetchall()
    previous = None
    for row in rows:
        record = {'id': row[0], 'ts': row[1], 'action': row[2], 'subject': row[3],
                  'data': row[4], 'previous_hash': previous}
        expected = hashlib.sha256(canonical_json(record).encode()).hexdigest()
        if row[5] != previous or row[6] != expected:
            raise RuntimeError(f'Audit chain is invalid at record {row[0]}; key operation aborted')
        previous = expected
    return previous


def append_audit(connection, ts, action, subject, data):
    previous_row = connection.execute('SELECT record_hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
    previous = previous_row[0] if previous_row else None
    payload = canonical_json(data)
    cursor = connection.execute(
        'INSERT INTO audit(ts,action,subject,data,previous_hash,record_hash) VALUES(?,?,?,?,?,NULL)',
        (ts, action, subject, payload, previous),
    )
    record = {'id': cursor.lastrowid, 'ts': ts, 'action': action, 'subject': subject,
              'data': payload, 'previous_hash': previous}
    digest = hashlib.sha256(canonical_json(record).encode()).hexdigest()
    connection.execute('UPDATE audit SET record_hash=? WHERE id=?', (digest, cursor.lastrowid))


def read_protected_key(path, *, exact_bytes=32, minimum_bytes=None):
    path = Path(path)
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f'Key must be a regular file, not a symlink: {path}')
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise RuntimeError(f'Key file must not be accessible to group or other users: {path}')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            key = stream.read(4097)
    except OSError as error:
        raise RuntimeError(f'Key file is unavailable: {path}') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if exact_bytes is not None and len(key) != exact_bytes:
        raise RuntimeError(f'Key must contain exactly {exact_bytes} random bytes: {path}')
    if minimum_bytes is not None and len(key) < minimum_bytes:
        raise RuntimeError(f'Key must contain at least {minimum_bytes} random bytes: {path}')
    if len(key) > 4096:
        raise RuntimeError(f'Key file is too large: {path}')
    return key


def backup_database(connection, database, *, label):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for _ in range(8):
        backup = database.with_name(f'{database.name}.pre-{label}-{stamp}-{secrets.token_hex(3)}.sqlite3')
        try:
            descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.close(descriptor)
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError('Could not reserve a unique protected database backup path')
    try:
        with sqlite3.connect(str(backup)) as destination:
            connection.backup(destination)
            destination.commit()
        os.chmod(backup, 0o600)
        with backup.open('rb') as stream:
            os.fsync(stream.fileno())
        return backup
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
