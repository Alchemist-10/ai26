"""Small RFC 6238 TOTP implementation with encrypted local secrets."""
import base64
import hashlib
import hmac
import os
import secrets
import stat
import struct
import time
from pathlib import Path
from urllib.parse import quote

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key():
    path_value = os.environ.get("AI26_AUTH_MFA_KEY_FILE")
    if not path_value:
        raise RuntimeError("MFA requires AI26_AUTH_MFA_KEY_FILE")
    return _read_key(Path(path_value))


def _read_key(path):
    path = Path(path)
    try:
        info = path.stat()
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise RuntimeError("MFA key file must not be accessible to group or other users")
        key = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("MFA key file is unavailable") from exc
    if len(key) != 32:
        raise RuntimeError("MFA key must contain exactly 32 random bytes")
    return key


def create_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret):
    return encrypt_secret_with_key(secret, _key())


def encrypt_secret_with_key(secret, key):
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, secret.encode("ascii"), b"AI26 TOTP v1")


def decrypt_secret(ciphertext):
    return decrypt_secret_with_key(ciphertext, _key())


def decrypt_secret_with_key(ciphertext, key):
    raw = bytes(ciphertext)
    if len(raw) < 29:
        raise RuntimeError("Stored MFA secret is invalid")
    try:
        return AESGCM(key).decrypt(raw[:12], raw[12:], b"AI26 TOTP v1").decode("ascii")
    except Exception as exc:
        raise RuntimeError("Stored MFA secret cannot be decrypted; verify the configured key") from exc


def code_at(secret, timestamp=None):
    timestamp = time.time() if timestamp is None else timestamp
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    counter = int(timestamp // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def verify_totp(secret, code, timestamp=None):
    return matched_totp_counter(secret, code, timestamp) is not None


def matched_totp_counter(secret, code, timestamp=None):
    """Return the matching RFC 6238 time-step counter, or None for an invalid code."""
    if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        return None
    timestamp = time.time() if timestamp is None else timestamp
    current = int(timestamp // 30)
    for counter in (current, current - 1, current + 1):
        if hmac.compare_digest(code, code_at(secret, counter * 30)):
            return counter
    return None


def provisioning_uri(secret, username):
    label = quote(f"AI26:{username}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer=Sakshi&algorithm=SHA1&digits=6&period=30"


def new_recovery_codes(count=10):
    return [secrets.token_hex(8).upper() for _ in range(count)]


def recovery_hash(code):
    return recovery_hash_with_key(code, _key())


def recovery_hash_with_key(code, key):
    canonical = "".join(char for char in str(code).upper() if char.isalnum())
    return hmac.new(key, b"AI26 recovery v1:" + canonical.encode("ascii", errors="ignore"), hashlib.sha256).hexdigest()
