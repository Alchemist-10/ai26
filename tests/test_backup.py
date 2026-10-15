import sqlite3
import os
import stat
import sys
import copy
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from backup import create_backup
from full_backup import create_full_backup, restore_full_backup
import full_backup
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

    def test_full_backup_restores_database_and_all_managed_media(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            backups = Path(folder) / "backups"
            root.mkdir()
            repository = Repository(root / "ai26.sqlite3")
            repository.set_setting("case", {"status": "before"})
            repository.close()
            expected = {
                "artifacts/frame.jpg": b"frame evidence",
                "sources/CAM-01/active.json": b"source manifest",
                "uploads/jobs/receipt.json": b"upload receipt",
                "models/weights.bin": b"model cache",
            }
            for relative, content in expected.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            snapshot = create_full_backup(root, backups, confirm_backend_stopped=True,
                                          owner_uid=os.getuid(), owner_gid=os.getgid())
            self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)
            self.assertEqual(snapshot.stat().st_uid, os.getuid())

            repository = Repository(root / "ai26.sqlite3")
            repository.set_setting("case", {"status": "after"})
            repository.close()
            (root / "artifacts/frame.jpg").write_bytes(b"changed")
            (root / "sources/CAM-01/active.json").unlink()
            (root / "uploads/jobs/receipt.json").unlink()
            (root / "models/weights.bin").unlink()
            (root / "models/new.bin").write_bytes(b"not in snapshot")
            Path(str(root / "ai26.sqlite3") + "-wal").write_bytes(b"stale wal")
            Path(str(root / "ai26.sqlite3") + "-shm").write_bytes(b"stale shm")

            restore_full_backup(snapshot, root, confirm_backend_stopped=True,
                                owner_uid=os.getuid(), owner_gid=os.getgid())
            self.assertFalse(Path(str(root / "ai26.sqlite3") + "-wal").exists())
            self.assertFalse(Path(str(root / "ai26.sqlite3") + "-shm").exists())
            repository = Repository(root / "ai26.sqlite3")
            try:
                self.assertEqual(repository.setting("case", {}), {"status": "before"})
            finally:
                repository.close()
            for relative, content in expected.items():
                self.assertEqual((root / relative).read_bytes(), content)
            self.assertFalse((root / "models/new.bin").exists())

    def test_full_restore_requires_stopped_confirmation_and_preserves_live_data_on_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            backups = Path(folder) / "backups"
            root.mkdir()
            Repository(root / "ai26.sqlite3").close()
            (root / "artifacts").mkdir()
            (root / "artifacts/keep.jpg").write_bytes(b"live")
            snapshot = create_full_backup(root, backups, confirm_backend_stopped=True)
            with self.assertRaises(ValueError):
                restore_full_backup(snapshot, root, confirm_backend_stopped=False)

            corrupted = backups / "corrupted.tar"
            with tarfile.open(snapshot, "r:") as source, tarfile.open(corrupted, "w") as output:
                for member in source.getmembers():
                    stream = source.extractfile(member)
                    content = stream.read() if stream else b""
                    if member.name == "artifacts/keep.jpg":
                        content = b"tampered"
                    changed_member = copy.copy(member)
                    changed_member.size = len(content)
                    output.addfile(changed_member, BytesIO(content))
            with self.assertRaisesRegex(ValueError, "(exceeds its declared size|integrity check failed)"):
                restore_full_backup(corrupted, root, confirm_backend_stopped=True)
            self.assertEqual((root / "artifacts/keep.jpg").read_bytes(), b"live")
            self.assertTrue((root / "ai26.sqlite3").is_file())

    def test_full_restore_rejects_path_traversal_before_touching_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            backups = Path(folder) / "backups"
            root.mkdir(); backups.mkdir()
            Repository(root / "ai26.sqlite3").close()
            (root / "artifacts").mkdir()
            (root / "artifacts/keep.jpg").write_bytes(b"live")
            malicious = backups / "traversal.tar"
            manifest = {"format": "ai26-managed-backup", "version": 1,
                        "files": [{"path": "../outside", "sha256": "0" * 64, "size": 1},
                                  {"path": "ai26.sqlite3", "sha256": "0" * 64, "size": 1}]}
            with tarfile.open(malicious, "w") as archive:
                raw = json.dumps(manifest).encode()
                info = tarfile.TarInfo("ai26-backup-manifest.json"); info.size = len(raw)
                archive.addfile(info, BytesIO(raw))
            with self.assertRaisesRegex(ValueError, "unsupported data path"):
                restore_full_backup(malicious, root, confirm_backend_stopped=True)
            self.assertEqual((root / "artifacts/keep.jpg").read_bytes(), b"live")
            self.assertFalse((Path(folder) / "outside").exists())

    def test_full_restore_rolls_back_if_install_fails_after_old_paths_move(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            backups = Path(folder) / "backups"
            root.mkdir()
            repository = Repository(root / "ai26.sqlite3")
            repository.set_setting("state", {"value": "saved"})
            repository.close()
            (root / "artifacts").mkdir()
            (root / "artifacts/state.jpg").write_bytes(b"saved artifact")
            snapshot = create_full_backup(root, backups, confirm_backend_stopped=True)
            repository = Repository(root / "ai26.sqlite3")
            repository.set_setting("state", {"value": "current"})
            repository.close()
            (root / "artifacts/state.jpg").write_bytes(b"current artifact")

            real_replace = full_backup.os.replace
            failed = False
            def fail_install_once(source, destination):
                nonlocal failed
                if not failed and Path(source).parent.name == "new" and Path(source).name == "ai26.sqlite3":
                    failed = True
                    raise OSError("simulated install failure")
                return real_replace(source, destination)
            with patch.object(full_backup.os, "replace", side_effect=fail_install_once):
                with self.assertRaisesRegex(OSError, "simulated install failure"):
                    restore_full_backup(snapshot, root, confirm_backend_stopped=True)

            repository = Repository(root / "ai26.sqlite3")
            try:
                self.assertEqual(repository.setting("state", {}), {"value": "current"})
            finally:
                repository.close()
            self.assertEqual((root / "artifacts/state.jpg").read_bytes(), b"current artifact")
