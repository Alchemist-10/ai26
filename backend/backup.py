"""Create verified SQLite snapshots while the Sakshi service is running."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile


def create_backup(source: Path, directory: Path, keep: int = 30,
                  owner_uid: int | None = None, owner_gid: int | None = None) -> Path:
    if type(keep) is not int or keep < 1:
        raise ValueError("Retention count must be a positive integer")
    if (owner_uid is None) != (owner_gid is None):
        raise ValueError("Both backup-file owner IDs must be provided together")
    source = Path(source).expanduser().resolve(strict=True)
    directory = Path(directory).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Source database must be a regular file")

    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("ai26-%Y%m%dT%H%M%S.%fZ.sqlite3")
    destination = directory / name
    fd, temporary_name = tempfile.mkstemp(prefix=".ai26-backup-", suffix=".sqlite3", dir=directory)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        source_uri = source.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True, timeout=10)) as source_db:
            with closing(sqlite3.connect(temporary, timeout=10)) as backup_db:
                source_db.backup(backup_db, pages=256, sleep=0.05)
                result = backup_db.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError("Backup integrity check failed")
                backup_db.commit()
        os.chmod(temporary, 0o600)
        if owner_uid is not None:
            os.chown(temporary, owner_uid, owner_gid)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        backups = sorted(directory.glob("ai26-*.sqlite3"), key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
        for stale in backups[keep:]:
            stale.unlink()
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--keep", type=int, default=30)
    parser.add_argument("--owner-uid", type=int)
    parser.add_argument("--owner-gid", type=int)
    args = parser.parse_args()
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    backup = create_backup(args.source, args.directory, args.keep, args.owner_uid, args.owner_gid)
    print(backup)


if __name__ == "__main__":
    main()
