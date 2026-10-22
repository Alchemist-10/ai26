"""Create and restore verified, stopped-service Sakshi data-volume snapshots."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile

FORMAT = "ai26-managed-backup"
VERSION = 1
MANAGED_DIRS = ("artifacts", "sources", "uploads", "models")
MANAGED_FILES = ("ai26.sqlite3",)
SWAP_TARGETS = (*MANAGED_FILES, *MANAGED_DIRS, "ai26.sqlite3-wal", "ai26.sqlite3-shm")
MANIFEST = "ai26-backup-manifest.json"
CHUNK_SIZE = 1024 * 1024
MAX_FILES = 1_000_000


def _digest_file(path):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return {"sha256": digest.hexdigest(), "size": size}


def _copy_database(source, destination):
    source = Path(source).resolve(strict=True)
    if not source.is_file() or source.is_symlink():
        raise ValueError("AI26 database must be a regular file")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)) as source_db:
        with closing(sqlite3.connect(destination, timeout=10)) as backup_db:
            source_db.backup(backup_db, pages=256, sleep=0.05)
            check = backup_db.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0] != "ok":
                raise sqlite3.DatabaseError("Database snapshot integrity check failed")
            backup_db.commit()
    os.chmod(destination, 0o600)


def _managed_files(root):
    files = []
    database = root / "ai26.sqlite3"
    if not database.exists():
        raise ValueError("AI26 database is missing from the data root")
    if database.is_symlink() or not database.is_file():
        raise ValueError("AI26 database must be a regular file")
    files.append((database, "ai26.sqlite3"))
    for name in MANAGED_DIRS:
        directory = root / name
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Managed data path {name} must be a directory")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Managed data contains a symbolic link: {path.relative_to(root)}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"Managed data contains a special file: {path.relative_to(root)}")
            files.append((path, path.relative_to(root).as_posix()))
    if len(files) > MAX_FILES:
        raise ValueError("Managed data contains too many files to archive")
    return files


def create_full_backup(data_root, directory, *, keep=30, owner_uid=None, owner_gid=None,
                       confirm_backend_stopped=False):
    """Snapshot DB plus artifacts, source releases, receipts and model cache.

    The caller must stop the backend first so the database and file tree describe
    one consistent point in time. Custom files mounted outside the data root are
    intentionally not included.
    """
    if not confirm_backend_stopped:
        raise ValueError("Stop the Sakshi backend and explicitly confirm before a full backup")
    if type(keep) is not int or keep < 1:
        raise ValueError("Retention count must be a positive integer")
    if (owner_uid is None) != (owner_gid is None):
        raise ValueError("Both backup-file owner IDs must be provided together")
    root = Path(data_root).expanduser().resolve(strict=True)
    directory = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("AI26 data root must be a directory")
    if directory == root or directory.is_relative_to(root):
        raise ValueError("Full backups must be stored outside the Sakshi data root")
    files = _managed_files(root)
    directory.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ai26-full-backup-") as work:
        snapshot = Path(work) / "ai26.sqlite3"
        _copy_database(root / "ai26.sqlite3", snapshot)
        sources = [(snapshot if rel == "ai26.sqlite3" else path, rel) for path, rel in files]
        entries = [{"path": rel, **_digest_file(path)} for path, rel in sources]
        manifest = {"format": FORMAT, "version": VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(), "files": entries}
        manifest_file = Path(work) / MANIFEST
        manifest_file.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.chmod(manifest_file, 0o600)
        name = datetime.now(timezone.utc).strftime("ai26-full-%Y%m%dT%H%M%S.%fZ.tar")
        destination = directory / name
        fd, temporary_name = tempfile.mkstemp(prefix=".ai26-full-", suffix=".tar", dir=directory)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            with tarfile.open(temporary, "w", format=tarfile.PAX_FORMAT) as archive:
                archive.add(manifest_file, arcname=MANIFEST, recursive=False)
                for path, rel in sources:
                    archive.add(path, arcname=rel, recursive=False)
            os.chmod(temporary, 0o600)
            if owner_uid is not None:
                os.chown(temporary, owner_uid, owner_gid)
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            backups = sorted(directory.glob("ai26-full-*.tar"),
                             key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
            for stale in backups[keep:]:
                stale.unlink()
            return destination
        finally:
            temporary.unlink(missing_ok=True)


def _allowed_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        return False
    return value in MANAGED_FILES or any(value.startswith(name + "/") for name in MANAGED_DIRS)


def _read_manifest(archive):
    try:
        if sum(member.name == MANIFEST for member in archive.getmembers()) != 1:
            raise ValueError("Full backup must contain exactly one manifest")
        member = archive.getmember(MANIFEST)
        if not member.isfile() or member.size > 32 * 1024 * 1024:
            raise ValueError("Backup manifest is invalid or too large")
        stream = archive.extractfile(member)
        manifest = json.load(stream)
    except (KeyError, OSError, json.JSONDecodeError, AttributeError) as error:
        raise ValueError("Full backup manifest is missing or invalid") from error
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        raise ValueError("Unsupported full backup format")
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) > MAX_FILES or not entries:
        raise ValueError("Full backup file manifest is invalid")
    expected = {}
    for entry in entries:
        if not isinstance(entry, dict) or not _allowed_path(entry.get("path")):
            raise ValueError("Full backup contains an unsupported data path")
        path, digest, size = entry.get("path"), entry.get("sha256"), entry.get("size")
        if (path in expected or not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
                or type(size) is not int or size < 0):
            raise ValueError("Full backup manifest entry is invalid")
        expected[path] = {"sha256": digest, "size": size}
    if "ai26.sqlite3" not in expected:
        raise ValueError("Full backup does not contain the Sakshi database")
    return expected


def _extract_verified(archive, expected, destination):
    members = {}
    for member in archive.getmembers():
        if member.name == MANIFEST:
            continue
        if not member.isfile() or not _allowed_path(member.name) or member.name in members:
            raise ValueError("Full backup contains an unsafe or duplicate archive entry")
        members[member.name] = member
    if set(members) != set(expected):
        raise ValueError("Full backup entries do not match its manifest")
    total = sum(entry["size"] for entry in expected.values())
    if total > 512 * 1024**3:
        raise ValueError("Full backup exceeds the 512 GiB restore limit")
    destination.mkdir(parents=True, exist_ok=False)
    for rel, entry in expected.items():
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        digest = hashlib.sha256()
        count = 0
        source = archive.extractfile(members[rel])
        with target.open("xb") as output:
            while chunk := source.read(CHUNK_SIZE):
                if count + len(chunk) > entry["size"]:
                    raise ValueError(f"Full backup entry exceeds its declared size: {rel}")
                output.write(chunk)
                digest.update(chunk)
                count += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(target, 0o600)
        if count != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise ValueError(f"Full backup integrity check failed for {rel}")
    with closing(sqlite3.connect((destination / "ai26.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True)) as database:
        check = database.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise sqlite3.DatabaseError("Restored database integrity check failed")
    for name in MANAGED_DIRS:
        (destination / name).mkdir(parents=True, exist_ok=True, mode=0o700)


def _remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def restore_full_backup(source, data_root, *, confirm_backend_stopped=False,
                        owner_uid=None, owner_gid=None):
    """Verify then transactionally replace managed data paths while stopped."""
    if not confirm_backend_stopped:
        raise ValueError("Stop the Sakshi backend and explicitly confirm before restoring")
    if (owner_uid is None) != (owner_gid is None):
        raise ValueError("Both restored-data owner IDs must be provided together")
    source_input = Path(source).expanduser()
    if source_input.is_symlink():
        raise ValueError("Full backup must be a regular archive file")
    source = source_input.resolve(strict=True)
    root = Path(data_root).expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError("Full backup must be a regular archive file")
    if source.is_relative_to(root):
        raise ValueError("Keep the full backup outside the Sakshi data root during restore")
    root.mkdir(parents=True, exist_ok=True)
    for name in SWAP_TARGETS:
        target = root / name
        if target.is_symlink() or (target.exists() and name in MANAGED_FILES and not target.is_file()) \
                or (target.exists() and name in MANAGED_DIRS and not target.is_dir()):
            raise ValueError(f"Existing managed path {name} has an unsupported type")
    staging = Path(tempfile.mkdtemp(prefix=".ai26-full-restore-", dir=root))
    new_data, old_data = staging / "new", staging / "old"
    moved, installed = [], []
    try:
        with tarfile.open(source, "r:") as archive:
            expected = _read_manifest(archive)
            total = sum(entry["size"] for entry in expected.values())
            if shutil.disk_usage(root).free < total:
                raise ValueError("Not enough free space to stage the verified full backup")
            _extract_verified(archive, expected, new_data)
        if owner_uid is not None:
            for path in [new_data, *new_data.rglob("*")]:
                os.chown(path, owner_uid, owner_gid)
                if path.is_dir():
                    os.chmod(path, 0o700)
                elif path.is_file():
                    os.chmod(path, 0o600)
        old_data.mkdir()
        for name in SWAP_TARGETS:
            current = root / name
            if current.exists():
                os.replace(current, old_data / name)
                moved.append(name)
        for name in (*MANAGED_FILES, *MANAGED_DIRS):
            os.replace(new_data / name, root / name)
            installed.append(name)
        return root
    except BaseException:
        for name in reversed(installed):
            _remove(root / name)
        for name in reversed(moved):
            saved = old_data / name
            if saved.exists():
                os.replace(saved, root / name)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    backup = subparsers.add_parser("create")
    backup.add_argument("--data-root", type=Path, required=True)
    backup.add_argument("--directory", type=Path, required=True)
    backup.add_argument("--keep", type=int, default=30)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--data-root", type=Path, required=True)
    for command in (backup, restore):
        command.add_argument("--confirm-backend-stopped", action="store_true")
        command.add_argument("--owner-uid", type=int)
        command.add_argument("--owner-gid", type=int)
    args = parser.parse_args()
    try:
        if args.operation == "create":
            result = create_full_backup(args.data_root, args.directory, keep=args.keep,
                                        owner_uid=args.owner_uid, owner_gid=args.owner_gid,
                                        confirm_backend_stopped=args.confirm_backend_stopped)
        else:
            result = restore_full_backup(args.source, args.data_root,
                                         owner_uid=args.owner_uid, owner_gid=args.owner_gid,
                                         confirm_backend_stopped=args.confirm_backend_stopped)
    except (OSError, ValueError, sqlite3.DatabaseError, tarfile.TarError) as error:
        parser.error(str(error))
    print(result)


if __name__ == "__main__":
    main()
