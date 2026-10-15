import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import mfa
from auth import AuthService
from auth_key_lock import api_lifetime_lock, verify_active_mfa_key
from repository import Repository
from rotate_mfa_key import rotate


class MfaKeyRotation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'ai26.sqlite3'
        self.old_key_path = self.root / 'old.key'
        self.new_key_path = self.root / 'new.key'
        self.recovery_output = self.root / 'recovery-codes.json'
        self.old_key = b'o' * 32
        self.new_key = b'n' * 32
        self.old_key_path.write_bytes(self.old_key)
        self.new_key_path.write_bytes(self.new_key)
        self.old_key_path.chmod(0o400)
        self.new_key_path.chmod(0o400)
        self.repo = Repository(self.database)
        self.addCleanup(self.repo.close)
        self.service = AuthService(self.repo)
        self.service.create_user('admin', 'Correct-Horse-Battery-Staple-26', 'admin')
        self.secret = mfa.create_secret()
        self.old_recovery = 'AABBCCDDEEFF0011'
        with patch.dict(os.environ, {'AI26_AUTH_MFA_KEY_FILE': str(self.old_key_path)}):
            recovery_hashes = json.dumps([mfa.recovery_hash(self.old_recovery)], separators=(',', ':'))
            with self.repo.lock, self.repo.db:
                self.repo.db.execute(
                    'INSERT INTO user_mfa(username,secret_ciphertext,enabled,recovery_hashes,updated_at,expires_at) VALUES(?,?,?,?,?,?)',
                    ('admin', mfa.encrypt_secret(self.secret), 1, recovery_hashes, time.time(), 0),
                )

    def test_rotation_reencrypts_secrets_reissues_codes_revokes_sessions_and_audits(self):
        now = time.time()
        with patch.dict(os.environ, {'AI26_AUTH_MFA_KEY_FILE': str(self.old_key_path)}):
            initial, reason = self.service.login(
                'admin', 'Correct-Horse-Battery-Staple-26', 'before-rotation', now,
                mfa_code=mfa.code_at(self.secret, now),
            )
        self.assertIsNone(reason)
        self.assertIsNotNone(initial)
        result = rotate(self.database, self.old_key_path, self.new_key_path, self.recovery_output)
        self.assertEqual(result['factors_reencrypted'], 1)
        self.assertEqual(result['enabled_users_reissued'], 1)
        self.assertEqual(result['sessions_revoked'], 1)
        self.assertEqual(self.recovery_output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(result['database_backup']).stat().st_mode & 0o777, 0o600)
        self.assertEqual(hashlib.sha256(self.new_key).hexdigest(), result['new_key_sha256'])

        row = self.repo.db.execute('SELECT * FROM user_mfa WHERE username=?', ('admin',)).fetchone()
        self.assertEqual(mfa.decrypt_secret_with_key(row['secret_ciphertext'], self.new_key), self.secret)
        self.assertEqual(self.repo.db.execute('SELECT count(*) FROM auth_sessions').fetchone()[0], 0)
        issued = json.loads(self.recovery_output.read_text())['users']['admin']
        self.assertEqual(len(issued), 10)
        with patch.dict(os.environ, {'AI26_AUTH_MFA_KEY_FILE': str(self.new_key_path)}):
            self.assertFalse(verify_active_mfa_key(self.database))
            _, rejected = self.service.login('admin', 'Correct-Horse-Battery-Staple-26', 'old-recovery',
                                             mfa_code=self.old_recovery)
            self.assertEqual(rejected, 'mfa_invalid')
            accepted, reason = self.service.login('admin', 'Correct-Horse-Battery-Staple-26', 'new-recovery',
                                                  mfa_code=issued[0])
            self.assertIsNone(reason)
            self.assertIsNotNone(accepted)
            _, reason = self.service.login('admin', 'Correct-Horse-Battery-Staple-26', 'new-recovery-reuse',
                                           mfa_code=issued[0])
            self.assertEqual(reason, 'mfa_invalid')

        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            with patch.dict(os.environ, {'AI26_AUTH_MFA_KEY_FILE': str(self.old_key_path)}):
                verify_active_mfa_key(self.database)
        backup = sqlite3.connect(result['database_backup'])
        try:
            old_ciphertext = backup.execute('SELECT secret_ciphertext FROM user_mfa WHERE username=?', ('admin',)).fetchone()[0]
            self.assertEqual(mfa.decrypt_secret_with_key(old_ciphertext, self.old_key), self.secret)
        finally:
            backup.close()
        self.assertEqual(self.repo.verify_audit_chain()['status'], 'valid')
        action = self.repo.db.execute("SELECT data FROM audit WHERE action='auth_mfa_key_rotated'").fetchone()
        self.assertEqual(json.loads(action['data'])['new_key_sha256'], hashlib.sha256(self.new_key).hexdigest())

    def test_rotation_is_rejected_while_any_api_holds_shared_database_lock(self):
        before = bytes(self.repo.db.execute('SELECT secret_ciphertext FROM user_mfa').fetchone()[0])
        with api_lifetime_lock(self.database):
            with self.assertRaisesRegex(RuntimeError, 'owns this database'):
                rotate(self.database, self.old_key_path, self.new_key_path, self.recovery_output)
        after = bytes(self.repo.db.execute('SELECT secret_ciphertext FROM user_mfa').fetchone()[0])
        self.assertEqual(after, before)
        self.assertFalse(self.recovery_output.exists())

    def test_bad_ciphertext_aborts_without_replacing_database_or_creating_output(self):
        with self.repo.lock, self.repo.db:
            self.repo.db.execute('UPDATE user_mfa SET secret_ciphertext=? WHERE username=?', (b'broken', 'admin'))
        before = bytes(self.repo.db.execute('SELECT secret_ciphertext FROM user_mfa').fetchone()[0])
        with self.assertRaisesRegex(RuntimeError, 'invalid|cannot be decrypted'):
            rotate(self.database, self.old_key_path, self.new_key_path, self.recovery_output)
        after = bytes(self.repo.db.execute('SELECT secret_ciphertext FROM user_mfa').fetchone()[0])
        self.assertEqual(after, before)
        self.assertFalse(self.recovery_output.exists())
        self.assertEqual(list(self.root.glob('*.pre-mfa-rotation-*.sqlite3')), [])

    def test_rotation_rejects_symlinked_key_files(self):
        key_link = self.root / 'old-key-link'
        key_link.symlink_to(self.old_key_path)
        with self.assertRaisesRegex(RuntimeError, 'unavailable|regular file'):
            rotate(self.database, key_link, self.new_key_path, self.recovery_output)
        self.assertFalse(self.recovery_output.exists())


if __name__ == '__main__':
    unittest.main()
