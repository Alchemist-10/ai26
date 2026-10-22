"""Create and verify portable signed checkpoints of the local audit-chain head."""
import argparse
import base64
import hashlib
import json
import os
import sqlite3
import stat
import time
from pathlib import Path
from urllib.parse import quote

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from repository import canonical_json

DOMAIN = b"AI26 audit checkpoint v1\n"


class AuditCheckpointError(ValueError):
    pass


def _raw_public(key):
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _load_private(path):
    try:
        target = Path(path)
        if os.name == "posix" and stat.S_IMODE(target.stat().st_mode) & 0o077:
            raise AuditCheckpointError("Audit checkpoint private key must not grant group or other access")
        key = serialization.load_pem_private_key(target.read_bytes(), password=None)
    except AuditCheckpointError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise AuditCheckpointError("Audit checkpoint private key is unavailable or invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AuditCheckpointError("Audit checkpoint private key must use Ed25519")
    return key


def _database(path):
    uri = "file:" + quote(str(Path(path).resolve())) + "?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True)
        db.row_factory = sqlite3.Row
        return db
    except sqlite3.Error as exc:
        raise AuditCheckpointError("Audit database is unavailable") from exc


def _chain_to(db, checkpoint_id):
    rows = db.execute(
        "SELECT id,ts,action,subject,data,previous_hash,record_hash FROM audit WHERE id<=? ORDER BY id",
        (checkpoint_id,),
    ).fetchall()
    previous = None
    for row in rows:
        record = {"id": row["id"], "ts": row["ts"], "action": row["action"],
                  "subject": row["subject"], "data": row["data"], "previous_hash": previous}
        expected = hashlib.sha256(canonical_json(record).encode()).hexdigest()
        if row["previous_hash"] != previous or row["record_hash"] != expected:
            raise AuditCheckpointError(f"Audit chain is invalid at record {row['id']}")
        previous = expected
    actual_id = rows[-1]["id"] if rows else 0
    if actual_id != checkpoint_id:
        raise AuditCheckpointError("Database does not contain the checkpointed audit record")
    return len(rows), previous


def create_checkpoint(database_path, private_key_path, created_at=None):
    """Return a signed snapshot of a verified audit-chain head."""
    private_key = _load_private(private_key_path)
    db = _database(database_path)
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        head = db.execute("SELECT id,record_hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        head_id, head_hash = (head["id"], head["record_hash"]) if head else (0, None)
        count, verified_hash = _chain_to(db, head_id)
        if verified_hash != head_hash:
            raise AuditCheckpointError("Audit chain head changed while creating checkpoint")
    except sqlite3.Error as exc:
        raise AuditCheckpointError("Database does not contain a readable Sakshi audit table") from exc
    finally:
        db.close()
    public = private_key.public_key()
    fingerprint = hashlib.sha256(_raw_public(public)).hexdigest()
    payload = {"format": "ai26-audit-checkpoint-v1", "created_at": time.time() if created_at is None else created_at,
               "database_schema_version": version, "audit_record_count": count,
               "audit_head_id": head_id, "audit_head_hash": head_hash,
               "key_fingerprint_sha256": fingerprint}
    signature = private_key.sign(DOMAIN + canonical_json(payload).encode())
    return {**payload, "signature_base64": base64.b64encode(signature).decode("ascii")}


def verify_checkpoint(checkpoint, public_key_path, database_path):
    if not isinstance(checkpoint, dict):
        raise AuditCheckpointError("Checkpoint must be a JSON object")
    fields = {"format", "created_at", "database_schema_version", "audit_record_count", "audit_head_id",
              "audit_head_hash", "key_fingerprint_sha256", "signature_base64"}
    if set(checkpoint) != fields or checkpoint.get("format") != "ai26-audit-checkpoint-v1":
        raise AuditCheckpointError("Checkpoint has unknown, missing, or unsupported fields")
    checkpoint_fingerprint = checkpoint["key_fingerprint_sha256"]
    if (not isinstance(checkpoint_fingerprint, str) or len(checkpoint_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in checkpoint_fingerprint)):
        raise AuditCheckpointError("Checkpoint trusted-key fingerprint is invalid")
    if isinstance(public_key_path, (str, os.PathLike)):
        trusted_paths = [public_key_path]
    else:
        trusted_paths = list(public_key_path)
    if not trusted_paths:
        raise AuditCheckpointError("At least one trusted public key is required")
    trusted_keys = {}
    try:
        for path in trusted_paths:
            public = serialization.load_pem_public_key(Path(path).read_bytes())
            if not isinstance(public, Ed25519PublicKey):
                raise AuditCheckpointError("Trusted public key must use Ed25519")
            fingerprint = hashlib.sha256(_raw_public(public)).hexdigest()
            trusted_keys[fingerprint] = public
    except AuditCheckpointError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise AuditCheckpointError("Trusted public key is unavailable or invalid") from exc
    public = trusted_keys.get(checkpoint_fingerprint)
    if public is None:
        raise AuditCheckpointError("No trusted public key fingerprint matches checkpoint")
    payload = {key: checkpoint[key] for key in fields if key != "signature_base64"}
    try:
        signature = base64.b64decode(checkpoint["signature_base64"], validate=True)
        public.verify(signature, DOMAIN + canonical_json(payload).encode())
    except (ValueError, InvalidSignature, TypeError) as exc:
        raise AuditCheckpointError("Audit checkpoint signature verification failed") from exc
    checkpoint_id = checkpoint["audit_head_id"]
    if not isinstance(checkpoint_id, int) or isinstance(checkpoint_id, bool) or checkpoint_id < 0:
        raise AuditCheckpointError("Checkpoint audit head ID is invalid")
    db = _database(database_path)
    try:
        count, head_hash = _chain_to(db, checkpoint_id)
        records_after = db.execute("SELECT count(*) FROM audit WHERE id>?", (checkpoint_id,)).fetchone()[0]
    except sqlite3.Error as exc:
        raise AuditCheckpointError("Database does not contain a readable Sakshi audit table") from exc
    finally:
        db.close()
    if count != checkpoint["audit_record_count"] or head_hash != checkpoint["audit_head_hash"]:
        raise AuditCheckpointError("Database audit history does not match the signed checkpoint")
    return {"status": "valid", "audit_head_id": checkpoint_id, "audit_head_hash": head_hash,
            "records_at_checkpoint": count, "records_after_checkpoint": records_after,
            "key_fingerprint_sha256": checkpoint_fingerprint}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="create a non-overwriting Ed25519 key pair")
    generate.add_argument("--private-key", required=True)
    generate.add_argument("--public-key", required=True)
    create = commands.add_parser("create", help="sign the current verified audit-chain head")
    create.add_argument("--database", required=True)
    create.add_argument("--private-key", required=True)
    create.add_argument("--output", required=True)
    verify = commands.add_parser("verify", help="verify a signed checkpoint against a database and trusted key(s)")
    verify.add_argument("--database", required=True)
    verify.add_argument("--checkpoint", required=True)
    verify.add_argument("--public-key", action="append", required=True,
                        help="trusted Ed25519 public key; repeat during/after rotation to retain old verification")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            from report_signing import generate_key_pair
            print(f"Generated Ed25519 key pair; public-key SHA-256: {generate_key_pair(args.private_key, args.public_key)}")
        elif args.command == "create":
            checkpoint = create_checkpoint(args.database, args.private_key)
            destination = Path(args.output)
            data = (json.dumps(checkpoint, sort_keys=True, indent=2) + "\n").encode()
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            print(f"Signed audit checkpoint head={checkpoint['audit_head_id']} hash={checkpoint['audit_head_hash']}")
        else:
            result = verify_checkpoint(json.loads(Path(args.checkpoint).read_text()), args.public_key, args.database)
            print("VALID " + json.dumps(result, sort_keys=True))
        return 0
    except (AuditCheckpointError, OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
