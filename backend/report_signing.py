"""Optional offline-verifiable Ed25519 signatures for immutable report JSON."""
import argparse
import base64
import hashlib
import os
import stat
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from repository import canonical_json

DOMAIN = b"AI26 evidence report signature v1\n"


class EvidenceSigningError(ValueError):
    pass


def _public_raw(public_key):
    return public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _signing_payload(report, key_id, fingerprint):
    unsigned = {key: value for key, value in report.items() if key not in {"signature", "package_hash"}}
    header = {"algorithm": "Ed25519", "key_id": key_id, "key_fingerprint_sha256": fingerprint}
    return DOMAIN + canonical_json({"report": unsigned, "signature": header}).encode("utf-8")


def _load_private_key(path):
    try:
        key_path = Path(path)
        if os.name == "posix" and stat.S_IMODE(key_path.stat().st_mode) & 0o077:
            raise EvidenceSigningError("Evidence signing key must not grant group or other access")
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    except EvidenceSigningError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise EvidenceSigningError("Evidence signing key is unavailable or invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise EvidenceSigningError("Evidence signing key must use Ed25519")
    return key


def sign_report(report):
    """Return a detached signature envelope, or None when signing is disabled."""
    key_path = os.environ.get("AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE")
    if not key_path:
        return None
    private_key = _load_private_key(key_path)
    public_key = private_key.public_key()
    fingerprint = hashlib.sha256(_public_raw(public_key)).hexdigest()
    key_id = os.environ.get("AI26_EVIDENCE_SIGNING_KEY_ID", fingerprint)
    if not key_id or len(key_id) > 128 or not key_id.isprintable():
        raise EvidenceSigningError("Evidence signing key ID must be 1–128 printable characters")
    signature = private_key.sign(_signing_payload(report, key_id, fingerprint))
    return {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "key_fingerprint_sha256": fingerprint,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def generate_key_pair(private_path, public_path):
    """Create an unencrypted PKCS8 private PEM (0600) and public PEM (0644)."""
    private_path, public_path = Path(private_path), Path(public_path)
    if private_path.resolve() == public_path.resolve():
        raise ValueError("Private and public key paths must differ")
    private_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    public_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(private_fd, "wb") as output:
            output.write(private_bytes)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        private_path.unlink(missing_ok=True)
        raise
    public_created = False
    try:
        public_fd = os.open(public_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        public_created = True
        with os.fdopen(public_fd, "wb") as output:
            output.write(public_bytes)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        private_path.unlink(missing_ok=True)
        if public_created:
            public_path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(_public_raw(public_key)).hexdigest()


def verify_report(report, trusted_public_key_path):
    """Verify report digest and Ed25519 signature against an out-of-band key."""
    if not isinstance(report, dict):
        raise EvidenceSigningError("Evidence report must be a JSON object")
    signature = report.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != "Ed25519":
        raise EvidenceSigningError("Evidence report has no supported digital signature")
    if set(signature) != {"algorithm", "key_id", "key_fingerprint_sha256", "signature_base64"}:
        raise EvidenceSigningError("Evidence report signature envelope has unknown or missing fields")
    key_id = signature.get("key_id")
    reported_fingerprint = signature.get("key_fingerprint_sha256")
    if not isinstance(key_id, str) or not key_id or len(key_id) > 128 or not key_id.isprintable():
        raise EvidenceSigningError("Evidence report has an invalid signing key ID")
    package_hash = report.get("package_hash")
    if not isinstance(package_hash, str) or len(package_hash) != 64:
        raise EvidenceSigningError("Evidence report package hash is missing")
    from hashlib import sha256
    packaged = {key: value for key, value in report.items() if key != "package_hash"}
    if sha256(canonical_json(packaged).encode("utf-8")).hexdigest() != package_hash:
        raise EvidenceSigningError("Evidence report package hash does not match")
    try:
        public_key = serialization.load_pem_public_key(Path(trusted_public_key_path).read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise EvidenceSigningError("Trusted public key is unavailable or invalid") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise EvidenceSigningError("Trusted public key must use Ed25519")
    fingerprint = hashlib.sha256(_public_raw(public_key)).hexdigest()
    if reported_fingerprint != fingerprint:
        raise EvidenceSigningError("Trusted public key fingerprint does not match report signature")
    try:
        if not isinstance(signature.get("signature_base64"), str):
            raise ValueError("signature_base64 is missing")
        raw_signature = base64.b64decode(signature["signature_base64"], validate=True)
        public_key.verify(raw_signature, _signing_payload(report, key_id, fingerprint))
    except (KeyError, ValueError, InvalidSignature) as exc:
        raise EvidenceSigningError("Evidence report signature verification failed") from exc
    return {"status": "valid", "report_id": report.get("report_id"), "key_id": signature.get("key_id"),
            "key_fingerprint_sha256": fingerprint}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="create a signing key pair without overwriting files")
    generate.add_argument("--private-key", required=True)
    generate.add_argument("--public-key", required=True)
    verify = commands.add_parser("verify", help="verify a signed report against a trusted public key")
    verify.add_argument("--report", required=True)
    verify.add_argument("--public-key", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            fingerprint = generate_key_pair(args.private_key, args.public_key)
            print(f"Generated Ed25519 key pair; public-key SHA-256: {fingerprint}")
            return 0
        import json
        result = verify_report(json.loads(Path(args.report).read_text()), args.public_key)
        print(f"VALID report={result['report_id']} key_id={result['key_id']} fingerprint={result['key_fingerprint_sha256']}")
        return 0
    except (EvidenceSigningError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
