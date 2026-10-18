import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
import main
import privacy
from auth_key_lock import api_lifetime_lock, verify_active_privacy_key
from repository import Repository
from rotate_privacy_key import rotate


class PrivacyKeyRotation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'ai26.sqlite3'
        self.old_key_path = self.root / 'old.key'
        self.new_key_path = self.root / 'new.key'
        self.old_key = b'o' * 40
        self.new_key = b'n' * 32
        self.old_key_path.write_bytes(self.old_key)
        self.new_key_path.write_bytes(self.new_key)
        self.old_key_path.chmod(0o400)
        self.new_key_path.chmod(0o400)
        self.repo = Repository(self.database)
        self.addCleanup(self.repo.close)
        self.env = patch.dict(os.environ, {
            'AI26_PRIVACY_ENABLED': '1',
            'AI26_PRIVACY_KEY_FILE': str(self.old_key_path),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.clear_privacy_cache)

    @staticmethod
    def clear_privacy_cache():
        privacy._cached_path = None
        privacy._cached_key = None

    def test_rotation_audits_fingerprints_backs_up_and_checks_new_key(self):
        alias_before = privacy.plate_alias('KA03MN1234')
        result = rotate(self.database, self.old_key_path, self.new_key_path)
        backup = Path(result['database_backup'])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result['old_key_sha256'], hashlib.sha256(self.old_key).hexdigest())
        self.assertEqual(result['new_key_sha256'], hashlib.sha256(self.new_key).hexdigest())
        self.assertEqual(self.repo.verify_audit_chain()['status'], 'valid')
        audit = self.repo.db.execute(
            "SELECT data FROM audit WHERE action='privacy_key_rotated' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        details = json.loads(audit['data'])
        self.assertTrue(details['analytics_aliases_changed'])
        self.assertEqual(details['new_key_sha256'], result['new_key_sha256'])
        backup_db = Repository(backup)
        try:
            self.assertEqual(backup_db.db.execute(
                "SELECT count(*) FROM audit WHERE action='privacy_key_rotated'"
            ).fetchone()[0], 0)
        finally:
            backup_db.close()

        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            verify_active_privacy_key(self.database)
        with patch.object(main, 'store', self.repo):
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                with TestClient(main.app):
                    pass
        with patch.dict(os.environ, {'AI26_PRIVACY_KEY_FILE': str(self.new_key_path)}):
            self.assertIsNone(verify_active_privacy_key(self.database))
            alias_after = privacy.plate_alias('KA03MN1234')
        self.assertNotEqual(alias_before, alias_after)

    def test_rotation_refuses_stale_key_and_live_api_without_database_change(self):
        rotate(self.database, self.old_key_path, self.new_key_path)
        stale = self.root / 'stale.key'
        stale.write_bytes(b's' * 32)
        stale.chmod(0o400)
        next_key = self.root / 'next.key'
        next_key.write_bytes(b'x' * 32)
        next_key.chmod(0o400)
        before = self.repo.verify_audit_chain()['head_hash']
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            rotate(self.database, self.old_key_path, next_key)
        self.assertEqual(self.repo.verify_audit_chain()['head_hash'], before)

        with api_lifetime_lock(self.database):
            with self.assertRaisesRegex(RuntimeError, 'owns this database'):
                rotate(self.database, self.new_key_path, next_key)
        self.assertEqual(self.repo.verify_audit_chain()['head_hash'], before)

    def test_rotation_rejects_symlink_key_without_writing_audit(self):
        link = self.root / 'new-link.key'
        link.symlink_to(self.new_key_path)
        before = self.repo.verify_audit_chain()['head_hash']
        with self.assertRaisesRegex(RuntimeError, 'unavailable|regular file'):
            rotate(self.database, self.old_key_path, link)
        self.assertEqual(self.repo.verify_audit_chain()['head_hash'], before)
        self.assertEqual(list(self.root.glob('*.pre-privacy-key-rotation-*.sqlite3')), [])


if __name__ == '__main__':
    unittest.main()
