"""Restore a verified SQLite snapshot while the Sakshi backend is stopped."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile


def restore_database(source: Path, destination: Path, *, confirm_backend_stopped: bool,
                     owner_uid: int | None = None, owner_gid: int | None = None) -> Path:
    if not confirm_backend_stopped:
        raise ValueError("Stop the Sakshi backend and explicitly confirm before restoring")
    source = Path(source).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser().resolve()
    if source == destination:
        raise ValueError("Backup and destination must be different files")
    if (owner_uid is None) != (owner_gid is None):
        raise ValueError("Both restored-file owner IDs must be provided together")
    if not source.is_file():
        raise ValueError("Backup must be a regular file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".ai26-restore-", suffix=".sqlite3", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        # The backup mount can be read-only; immutable mode avoids asking SQLite
        # to create lock/shared-memory sidecars beside an unchanging snapshot.
        with closing(sqlite3.connect(source.as_uri()+"?mode=ro&immutable=1", uri=True, timeout=10)) as backup_db:
            result = backup_db.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError("Backup integrity check failed")
            with closing(sqlite3.connect(temporary, timeout=10)) as restored_db:
                backup_db.backup(restored_db, pages=256, sleep=0.05)
                restored_db.commit()
        os.chmod(temporary, 0o600)
        if owner_uid is not None:
            os.chown(temporary, owner_uid, owner_gid)
        for suffix in ("-wal", "-shm"):
            Path(str(destination)+suffix).unlink(missing_ok=True)
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("/app/data/ai26.sqlite3"))
    parser.add_argument("--confirm-backend-stopped", action="store_true")
    parser.add_argument("--owner-uid", type=int)
    parser.add_argument("--owner-gid", type=int)
    args = parser.parse_args()
    try:
        restored = restore_database(args.source, args.destination,
                                    confirm_backend_stopped=args.confirm_backend_stopped,
                                    owner_uid=args.owner_uid, owner_gid=args.owner_gid)
    except ValueError as error:
        parser.error(str(error))
    print(restored)


if __name__ == "__main__":
    main()
