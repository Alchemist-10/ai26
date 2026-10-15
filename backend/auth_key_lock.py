"""Coordinate offline MFA key rotation with API process lifetimes."""
from contextlib import contextmanager
import hashlib
import fcntl
import json
import hmac
import os
from pathlib import Path


def lock_path(database):
    return Path(database).resolve().parent / '.mfa-key-rotation.lock'


@contextmanager
def _lock(database, operation, nonblocking):
    path = lock_path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+')
    flags = fcntl.LOCK_SH if operation == 'API' else fcntl.LOCK_EX
    if nonblocking:
        flags |= fcntl.LOCK_NB
    try:
        try:
            fcntl.flock(handle, flags)
        except BlockingIOError as error:
            raise RuntimeError(f'Cannot start {operation}: an API or another offline key operation owns this database') from error
        yield handle
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()


def api_lifetime_lock(database):
    """Nonblocking shared lock held for the entire serving lifetime."""
    return _lock(database, 'API', True)


def exclusive_rotation_lock(database):
    """Nonblocking exclusive lock for offline key operations (legacy name)."""
    return exclusive_key_maintenance_lock(database)


def exclusive_key_maintenance_lock(database):
    """Nonblocking exclusive lock held by offline key maintenance commands."""
    return _lock(database, 'offline key maintenance', True)


def verify_active_mfa_key(database):
    """Block service startup until configuration follows a completed rotation."""
    import sqlite3
    with sqlite3.connect(str(database)) as connection:
        row = connection.execute(
            "SELECT data FROM audit WHERE action='auth_mfa_key_rotated' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return
    expected = json.loads(row[0]).get('new_key_sha256')
    configured = os.environ.get('AI26_AUTH_MFA_KEY_FILE')
    if not configured:
        raise RuntimeError('MFA key rotation is recorded; set AI26_AUTH_MFA_KEY_FILE to the new protected key before starting')
    try:
        from mfa import _read_key
        actual = hashlib.sha256(_read_key(configured)).hexdigest()
    except RuntimeError as error:
        raise RuntimeError('MFA key rotation is recorded; the configured key is unavailable. Set AI26_AUTH_MFA_KEY_FILE to the new protected key.') from error
    if actual != expected:
        raise RuntimeError('MFA key rotation is recorded; the configured key does not match. Set AI26_AUTH_MFA_KEY_FILE to the new protected key.')


def verify_active_privacy_key(database):
    """When privacy mode is enabled, require the latest audited privacy key."""
    if os.environ.get('AI26_PRIVACY_ENABLED', '0') != '1':
        return
    import sqlite3
    with sqlite3.connect(str(database)) as connection:
        row = connection.execute(
            "SELECT data FROM audit WHERE action='privacy_key_rotated' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return
    try:
        expected = json.loads(row[0]).get('new_key_sha256')
        from privacy import _key
        actual = hashlib.sha256(_key()).hexdigest()
    except (RuntimeError, ValueError, TypeError) as error:
        raise RuntimeError('Privacy-key rotation is recorded; set AI26_PRIVACY_KEY_FILE to the new protected key.') from error
    if not isinstance(expected, str) or not hmac.compare_digest(actual, expected):
        raise RuntimeError('Privacy-key rotation is recorded; the configured key does not match. Set AI26_PRIVACY_KEY_FILE to the new protected key.')
