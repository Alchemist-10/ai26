"""Single-process local authentication, role checks, case scope, and audit context."""
import hashlib
import hmac
import os
import re
import secrets
import time
from pathlib import Path


ROLES = {"admin", "operator", "analyst", "viewer"}
PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60
FAILURE_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_FAILURES = 10
SESSION_COOKIE = "ai26_session"
CSRF_HEADER = "x-ai26-csrf-token"
CASE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}\Z")
PURPOSES = {"investigation", "traffic_analysis", "incident_response", "system_test"}
_USERNAME_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{2,31}\Z")


class AuthenticationError(ValueError):
    pass


def auth_enabled():
    return os.environ.get("AI26_AUTH_ENABLED", "0") == "1"


def cookie_secure():
    return os.environ.get("AI26_AUTH_COOKIE_SECURE", "0") == "1"


def _password(value):
    if not isinstance(value, str) or not 14 <= len(value) <= 256:
        raise AuthenticationError("Password must be between 14 and 256 characters")
    return value.encode("utf-8")


def _username(value):
    if not isinstance(value, str):
        raise AuthenticationError("Username must use 3–32 letters, digits, dots, underscores, or hyphens")
    normalized = value.strip().casefold()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise AuthenticationError("Username must use 3–32 letters, digits, dots, underscores, or hyphens")
    return normalized


def _case_ids(values):
    if values is None:
        return None
    if not isinstance(values, (list, tuple, set)) or len(values) > 100:
        raise AuthenticationError("Case access must contain at most 100 case IDs")
    normalized = set()
    for value in values:
        if not isinstance(value, str):
            raise AuthenticationError("Every case ID must be text")
        case_id = value.strip()
        if not CASE_PATTERN.fullmatch(case_id):
            raise AuthenticationError("Case IDs must use 3–64 letters, digits, dots, underscores, or hyphens")
        normalized.add(case_id)
    return sorted(normalized)


def _derive(password, salt, iterations=PASSWORD_ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", _password(password), salt, iterations, dklen=32)


def _user_summary(row):
    return {"username": row["username"], "role": row["role"], "disabled": bool(row["disabled"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


class AuthService:
    def __init__(self, repository):
        self.repository = repository

    def ensure_bootstrap_admin(self):
        if not auth_enabled():
            return
        with self.repository.lock:
            if self.repository.db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return
        password_path = os.environ.get("AI26_ADMIN_BOOTSTRAP_PASSWORD_FILE")
        if not password_path:
            raise RuntimeError("Authentication is enabled but no bootstrap administrator password file is configured")
        try:
            password = Path(password_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError("Authentication is enabled but the bootstrap administrator secret is unavailable") from exc
        _password(password)
        username = _username(os.environ.get("AI26_ADMIN_USERNAME", "admin"))
        salt = secrets.token_bytes(16)
        digest = _derive(password, salt)
        now = time.time()
        with self.repository.lock, self.repository.db:
            if not self.repository.db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                self.repository.db.execute(
                    "INSERT INTO users(username,password_salt,password_hash,iterations,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (username, salt, digest, PASSWORD_ITERATIONS, "admin", now, now),
                )
                self.repository._append_audit(now, "auth_bootstrap_admin", username, {"role": "admin"})

    def user_count(self):
        with self.repository.lock:
            return self.repository.db.execute("SELECT count(*) FROM users WHERE disabled=0").fetchone()[0]

    def users(self):
        with self.repository.lock:
            rows = self.repository.db.execute(
                "SELECT username,role,disabled,created_at,updated_at FROM users ORDER BY username COLLATE NOCASE"
            ).fetchall()
            cases = self.repository.db.execute("SELECT username,case_id FROM user_case_access ORDER BY case_id").fetchall()
        by_user = {}
        for row in cases:
            by_user.setdefault(row["username"], []).append(row["case_id"])
        return [{**_user_summary(row), "case_ids": by_user.get(row["username"], [])} for row in rows]

    def case_ids(self, username):
        with self.repository.lock:
            rows = self.repository.db.execute("SELECT case_id FROM user_case_access WHERE username=? ORDER BY case_id", (username,)).fetchall()
        return [row[0] for row in rows]

    def can_access_case(self, username, case_id, role=None):
        if role == "admin":
            return True
        with self.repository.lock:
            return self.repository.db.execute(
                "SELECT 1 FROM user_case_access WHERE username=? AND case_id=?", (username, case_id)
            ).fetchone() is not None

    def create_user(self, username, password, role, now=None, case_ids=None):
        username, password = _username(username), _password(password)
        if role not in ROLES:
            raise AuthenticationError("Role must be admin, operator, analyst, or viewer")
        case_ids = _case_ids(case_ids) or []
        salt = secrets.token_bytes(16)
        digest = _derive(password.decode("utf-8"), salt)
        now = time.time() if now is None else now
        with self.repository.lock, self.repository.db:
            self.repository.db.execute(
                "INSERT INTO users(username,password_salt,password_hash,iterations,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (username, salt, digest, PASSWORD_ITERATIONS, role, now, now),
            )
            self.repository.db.executemany("INSERT INTO user_case_access(username,case_id,created_at) VALUES(?,?,?)",
                                           [(username, case_id, now) for case_id in case_ids])
            self.repository._append_audit(now, "auth_user_created", username, {"role": role, "case_ids": case_ids})
        return {"username": username, "role": role, "disabled": False, "case_ids": case_ids,
                "created_at": now, "updated_at": now}

    def update_user(self, username, role=None, disabled=None, now=None, case_ids=None):
        username = _username(username)
        case_ids = _case_ids(case_ids)
        now = time.time() if now is None else now
        if role is not None and role not in ROLES:
            raise AuthenticationError("Role must be admin, operator, analyst, or viewer")
        if disabled is not None and not isinstance(disabled, bool):
            raise AuthenticationError("disabled must be a boolean")
        with self.repository.lock, self.repository.db:
            current = self.repository.db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not current:
                return None
            next_role = current["role"] if role is None else role
            next_disabled = bool(current["disabled"]) if disabled is None else disabled
            current_case_ids = [row[0] for row in self.repository.db.execute(
                "SELECT case_id FROM user_case_access WHERE username=? ORDER BY case_id", (username,)
            ).fetchall()]
            next_case_ids = current_case_ids if case_ids is None else case_ids
            if current["role"] == "admin" and not current["disabled"] and (next_role != "admin" or next_disabled):
                remaining = self.repository.db.execute(
                    "SELECT count(*) FROM users WHERE role='admin' AND disabled=0 AND username<>?", (username,)
                ).fetchone()[0]
                if remaining == 0:
                    raise AuthenticationError("The last active administrator cannot be disabled or demoted")
            self.repository.db.execute("UPDATE users SET role=?,disabled=?,updated_at=? WHERE username=?",
                                       (next_role, int(next_disabled), now, username))
            if case_ids is not None and next_case_ids != current_case_ids:
                self.repository.db.execute("DELETE FROM user_case_access WHERE username=?", (username,))
                self.repository.db.executemany("INSERT INTO user_case_access(username,case_id,created_at) VALUES(?,?,?)",
                                               [(username, case_id, now) for case_id in next_case_ids])
            if next_disabled or next_role != current["role"] or next_case_ids != current_case_ids:
                self.repository.db.execute("DELETE FROM auth_sessions WHERE username=?", (username,))
            self.repository._append_audit(now, "auth_user_updated", username,
                                          {"role": next_role, "disabled": next_disabled, "case_ids": next_case_ids})
            updated = self.repository.db.execute(
                "SELECT username,role,disabled,created_at,updated_at FROM users WHERE username=?", (username,)
            ).fetchone()
        return {**_user_summary(updated), "case_ids": next_case_ids}

    def reset_password(self, username, password, now=None):
        username, password = _username(username), _password(password)
        salt = secrets.token_bytes(16)
        digest = _derive(password.decode("utf-8"), salt)
        now = time.time() if now is None else now
        with self.repository.lock, self.repository.db:
            current = self.repository.db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
            if not current:
                return False
            self.repository.db.execute(
                "UPDATE users SET password_salt=?,password_hash=?,iterations=?,updated_at=? WHERE username=?",
                (salt, digest, PASSWORD_ITERATIONS, now, username),
            )
            self.repository.db.execute("DELETE FROM auth_sessions WHERE username=?", (username,))
            self.repository._append_audit(now, "auth_password_reset", username, {})
        return True

    def login(self, username, password, client_address, now=None):
        now = time.time() if now is None else now
        normalized = _username(username)
        ip_hash = hashlib.sha256((client_address or "unknown").encode()).hexdigest()
        with self.repository.lock:
            recent = self.repository.db.execute(
                "SELECT count(*) FROM auth_login_failures WHERE client_hash=? AND failed_at>?",
                (ip_hash, now - FAILURE_WINDOW_SECONDS),
            ).fetchone()[0]
            row = self.repository.db.execute("SELECT * FROM users WHERE username=?", (normalized,)).fetchone()
        if recent >= MAX_LOGIN_FAILURES:
            return None, "limited"
        salt = row["password_salt"] if row else b"AI26 dummy salt!!"
        iterations = row["iterations"] if row else PASSWORD_ITERATIONS
        expected = row["password_hash"] if row else b"\0" * 32
        try:
            actual = _derive(password, salt, iterations)
            password_valid = hmac.compare_digest(actual, expected)
        except AuthenticationError:
            _derive("invalid password placeholder", salt, iterations)
            password_valid = False
        if not row or not password_valid or row["disabled"]:
            with self.repository.lock, self.repository.db:
                self.repository.db.execute("INSERT INTO auth_login_failures(client_hash,failed_at) VALUES(?,?)", (ip_hash, now))
                self.repository.db.execute("DELETE FROM auth_login_failures WHERE failed_at<=?", (now - FAILURE_WINDOW_SECONDS,))
            return None, "invalid"
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = now + SESSION_SECONDS
        with self.repository.lock, self.repository.db:
            current = self.repository.db.execute("SELECT * FROM users WHERE username=?", (normalized,)).fetchone()
            if not current or current["disabled"]:
                return None, "invalid"
            self.repository.db.execute("INSERT INTO auth_sessions VALUES(?,?,?,?,?)",
                                       (token_hash, normalized, csrf, now, expires))
            self.repository.db.execute("DELETE FROM auth_login_failures WHERE client_hash=?", (ip_hash,))
            self.repository._append_audit(now, "auth_login", normalized, {"role": current["role"]})
        return {"token": token, "csrf_token": csrf, "expires_at": expires,
                "user": {"username": current["username"], "role": current["role"]}}, None

    def session(self, token, now=None):
        if not isinstance(token, str) or len(token) > 128:
            return None
        now = time.time() if now is None else now
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.repository.lock:
            row = self.repository.db.execute(
                "SELECT s.csrf_token,s.expires_at,u.username,u.role,u.disabled FROM auth_sessions s "
                "JOIN users u ON u.username=s.username WHERE s.token_hash=?", (token_hash,)
            ).fetchone()
        if not row or row["expires_at"] <= now or row["disabled"]:
            return None
        return {"username": row["username"], "role": row["role"], "csrf_token": row["csrf_token"],
                "expires_at": row["expires_at"], "token_hash": token_hash}

    def logout(self, token, now=None):
        if not isinstance(token, str) or len(token) > 128:
            return
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = time.time() if now is None else now
        with self.repository.lock, self.repository.db:
            row = self.repository.db.execute("SELECT username FROM auth_sessions WHERE token_hash=?", (token_hash,)).fetchone()
            self.repository.db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
            if row:
                self.repository._append_audit(now, "auth_logout", row["username"], {})

    def audit_sensitive_access(self, actor, case_id, purpose, method, route, now=None):
        self.repository.audit_sensitive_access(actor["username"], case_id, purpose, method, route,
                                               time.time() if now is None else now)
