import sqlite3
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from backup import create_backup
from repository import Repository
from restore import restore_database


class DatabaseBackup(unittest.TestCase):
    def test_online_snapshot_is_integral_and_preserves_committed_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "live.sqlite3"
            repository = Repository(source)
            try:
                repository.set_setting("backup-test", {"value": "committed"})
                destination = create_backup(source, root / "backups", owner_uid=os.getuid(), owner_gid=os.getgid())
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
                self.assertEqual(destination.stat().st_uid, os.getuid())
                copied = Repository(destination)
                try:
                    self.assertEqual(copied.setting("backup-test", {}), {"value": "committed"})
                finally:
                    copied.close()
                with sqlite3.connect(destination) as database:
                    self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                repository.close()

    def test_backup_rotation_keeps_requested_newest_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "live.sqlite3"
            repository = Repository(source)
            try:
                repository.set_setting("value", 1)
                directory = root / "backups"
                created = [create_backup(source, directory, keep=2) for _ in range(3)]
                files = sorted(directory.glob("ai26-*.sqlite3"))
                self.assertEqual(len(files), 2)
                self.assertTrue(created[-1].exists())
            finally:
                repository.close()

    def test_invalid_source_and_retention_do_not_create_a_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / "backups"
            with self.assertRaises(FileNotFoundError):
                create_backup(root / "missing.sqlite3", directory)
            source = root / "live.sqlite3"
            Repository(source).close()
            with self.assertRaises(ValueError):
                create_backup(source, directory, keep=0)
            self.assertFalse(directory.exists())

    def test_restore_requires_stopped_confirmation_and_replaces_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = Repository(root / "original.sqlite3")
            destination = Repository(root / "current.sqlite3")
            try:
                original.set_setting("state", {"source": "backup"})
                destination.set_setting("state", {"source": "current"})
                snapshot = create_backup(root / "original.sqlite3", root / "backups")
                with self.assertRaises(ValueError):
                    restore_database(snapshot, root / "current.sqlite3", confirm_backend_stopped=False)
                Path(str(root / "current.sqlite3")+"-wal").write_bytes(b"stale")
                destination.close()
                restore_database(snapshot, root / "current.sqlite3", confirm_backend_stopped=True)
                self.assertFalse(Path(str(root / "current.sqlite3")+"-wal").exists())
                restored = Repository(root / "current.sqlite3")
                try:
                    self.assertEqual(restored.setting("state", {}), {"source": "backup"})
                finally:
                    restored.close()
            finally:
                original.close()
