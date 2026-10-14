import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from audit_checkpoint import AuditCheckpointError, create_checkpoint, verify_checkpoint
from report_signing import generate_key_pair
from repository import Repository


class AuditCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db_path = root / "state.sqlite3"
        self.private = root / "private.pem"
        self.public = root / "public.pem"
        generate_key_pair(self.private, self.public)
        self.repo = Repository(self.db_path)
        self.addCleanup(self.repo.close)

    def add_audit(self, action="operator_action"):
        with self.repo.lock, self.repo.db:
            self.repo._append_audit(123.0, action, "admin", {"ok": True})

    def test_checkpoint_round_trip_and_append_only_growth(self):
        self.add_audit()
        checkpoint = create_checkpoint(self.db_path, self.private, created_at=456.0)
        self.add_audit("later_action")
        result = verify_checkpoint(checkpoint, self.public, self.db_path)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["records_at_checkpoint"], 1)
        self.assertEqual(result["records_after_checkpoint"], 1)

    def test_tampered_checkpoint_and_database_are_rejected(self):
        self.add_audit()
        checkpoint = create_checkpoint(self.db_path, self.private)
        tampered = {**checkpoint, "audit_head_id": 4}
        with self.assertRaisesRegex(AuditCheckpointError, "signature"):
            verify_checkpoint(tampered, self.public, self.db_path)
        with self.repo.lock, self.repo.db:
            self.repo.db.execute("UPDATE audit SET subject='changed' WHERE id=1")
        with self.assertRaisesRegex(AuditCheckpointError, "invalid"):
            verify_checkpoint(checkpoint, self.public, self.db_path)

    def test_wrong_key_and_unverified_chain_cannot_be_checkpointed(self):
        wrong_public = Path(self.temp.name) / "wrong-public.pem"
        wrong_private = Path(self.temp.name) / "wrong-private.pem"
        generate_key_pair(wrong_private, wrong_public)
        self.add_audit()
        checkpoint = create_checkpoint(self.db_path, self.private)
        with self.assertRaisesRegex(AuditCheckpointError, "fingerprint"):
            verify_checkpoint(checkpoint, wrong_public, self.db_path)
        with self.repo.lock, self.repo.db:
            self.repo.db.execute("UPDATE audit SET record_hash='bad' WHERE id=1")
        with self.assertRaisesRegex(AuditCheckpointError, "invalid"):
            create_checkpoint(self.db_path, self.private)

    @unittest.skipIf(os.name != "posix", "POSIX file permissions required")
    def test_private_key_permissions_are_enforced(self):
        self.private.chmod(0o644)
        with self.assertRaisesRegex(AuditCheckpointError, "group or other"):
            create_checkpoint(self.db_path, self.private)


if __name__ == "__main__":
    unittest.main()
