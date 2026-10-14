import hashlib
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
import main
import events
from auth import AuthService, AuthenticationError, CSRF_HEADER, MAX_LOGIN_FAILURES, SESSION_COOKIE
from repository import Repository


class Authentication(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repo = Repository(Path(self.folder.name) / "auth.sqlite3")
        self.addCleanup(self.repo.close)
        self._patches = [patch.object(main, "store", self.repo), patch.object(events, "store", self.repo)]
        for item in self._patches:
            item.start()
            self.addCleanup(item.stop)
        self.env = patch.dict(os.environ, {"AI26_AUTH_ENABLED": "1", "AI26_AUTH_COOKIE_SECURE": "1", "AI26_PROCESSING_ENABLED": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.auth = AuthService(self.repo)
        self.client = TestClient(main.app, base_url="https://testserver")

    def create(self, username="admin", role="admin"):
        return self.auth.create_user(username, "Correct-Horse-Battery-Staple-26", role)

    def login(self, username="admin"):
        response = self.client.post("/api/auth/login", json={"username": username, "password": "Correct-Horse-Battery-Staple-26"})
        if response.status_code == 200:
            self.csrf = response.json()["csrf_token"]
        return response

    def csrf_headers(self):
        return {CSRF_HEADER: self.csrf}

    def test_schema_five_bootstrap_is_persistent_and_never_resets_password(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bootstrap-password"
            path.write_text("Bootstrap-Correct-Horse-42\n")
            repository = Repository(Path(folder) / "bootstrap.sqlite3")
            try:
                with patch.dict(os.environ, {"AI26_AUTH_ENABLED": "1", "AI26_ADMIN_BOOTSTRAP_PASSWORD_FILE": str(path)}):
                    service = AuthService(repository)
                    service.ensure_bootstrap_admin()
                    service.ensure_bootstrap_admin()
                    self.assertEqual(service.user_count(), 1)
                    self.assertIsNotNone(service.login("admin", "Bootstrap-Correct-Horse-42", "testhost")[0])
                    self.assertIsNone(service.login("admin", "Different-Correct-Horse-42", "otherhost")[0])
                self.assertEqual(repository.schema_version, 5)
                self.assertEqual(repository.db.execute("PRAGMA user_version").fetchone()[0], 5)
            finally:
                repository.close()

    def test_bootstrap_requires_a_strong_secret_file(self):
        with patch.dict(os.environ, {"AI26_AUTH_ENABLED": "1"}, clear=False):
            os.environ.pop("AI26_ADMIN_BOOTSTRAP_PASSWORD_FILE", None)
            with self.assertRaisesRegex(RuntimeError, "no bootstrap administrator"):
                self.auth.ensure_bootstrap_admin()

    def test_login_cookie_role_gate_case_scope_csrf_and_audit(self):
        self.create("analyst_one", "analyst")
        response = self.login("analyst_one")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "analyst")
        set_cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", set_cookie)
        self.assertIn("secure", set_cookie)
        self.assertIn("samesite=strict", set_cookie)
        self.assertIn("path=/api", set_cookie)
        csrf = response.json()["csrf_token"]
        self.assertEqual(self.client.get("/api/auth/me").json()["csrf_token"], csrf)

        self.assertEqual(self.client.get("/api/cameras").status_code, 200)
        missing_scope = self.client.get("/api/events")
        self.assertEqual(missing_scope.status_code, 422)
        headers = {"X-AI26-Case-ID": "CASE-2026-01", "X-AI26-Purpose": "investigation"}
        scoped = self.client.get("/api/events", headers=headers)
        self.assertEqual(scoped.status_code, 200)
        self.assertEqual(self.repo.verify_audit_chain()["status"], "valid")
        row = self.repo.db.execute("SELECT action,subject,data FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row["action"], "sensitive_access")
        self.assertEqual(row["subject"], "analyst_one")
        self.assertIn("CASE-2026-01", row["data"])
        self.assertIn("investigation", row["data"])
        self.client.get("/api/events", headers=headers)
        coalesced = self.repo.db.execute("SELECT count(*) FROM audit WHERE action='sensitive_access'").fetchone()[0]
        self.assertEqual(coalesced, 1)
        alternate = {**headers, "X-AI26-Purpose": "traffic_analysis"}
        self.client.get("/api/events", headers=alternate)
        self.assertEqual(self.repo.db.execute("SELECT count(*) FROM audit WHERE action='sensitive_access'").fetchone()[0], 2)

        self.assertEqual(self.client.put("/api/rules", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout", headers={CSRF_HEADER: csrf}).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_viewer_cannot_query_or_mutate_but_health_stays_public(self):
        self.create("viewer_one", "viewer")
        self.assertEqual(self.login("viewer_one").status_code, 200)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/cameras").status_code, 200)
        self.assertEqual(self.client.get("/api/events", headers={"X-AI26-Case-ID":"CASE-55","X-AI26-Purpose":"system_test"}).status_code, 403)

    def test_user_management_and_last_admin_protection(self):
        self.create()
        self.assertEqual(self.login().status_code, 200)
        created = self.client.post("/api/auth/users", json={
            "username": "operator_one", "password": "Operator-Correct-Horse-2026", "role": "operator",
        }, headers=self.csrf_headers())
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["role"], "operator")
        last_admin = self.client.patch("/api/auth/users/admin", json={"disabled": True}, headers=self.csrf_headers())
        self.assertEqual(last_admin.status_code, 409)
        self.assertEqual(self.client.patch("/api/auth/users/operator_one", json={"disabled": True}, headers=self.csrf_headers()).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/users/operator_one/password", json={"password":"New-Operator-Horse-2026"}, headers=self.csrf_headers()).status_code, 200)

    def test_login_throttle_and_expired_sessions(self):
        self.create()
        client_hash = hashlib.sha256(b"testclient").hexdigest()
        now = time.time()
        self.repo.db.executemany("INSERT INTO auth_login_failures(client_hash,failed_at) VALUES(?,?)",
                                 [(client_hash, now)] * MAX_LOGIN_FAILURES)
        limited = self.login()
        self.assertEqual(limited.status_code, 429)
        self.repo.db.execute("DELETE FROM auth_login_failures")
        self.repo.db.commit()
        result = self.login()
        self.assertEqual(result.status_code, 200)
        token = self.client.cookies.get(SESSION_COOKIE)
        self.assertIsNotNone(self.auth.session(token))
        self.assertIsNone(self.auth.session(token, now + 9 * 60 * 60))

    def test_invalid_username_password_and_user_role_are_rejected(self):
        with self.assertRaises(AuthenticationError):
            self.auth.create_user("x", "short", "superuser")
        malformed = self.client.post("/api/auth/login", json={"username": "x", "password": "no"})
        self.assertEqual(malformed.status_code, 422)
        invalid = self.client.post("/api/auth/login", json={"username": "admin", "password": "Wrong-Correct-Horse-2026"})
        self.assertEqual(invalid.status_code, 401)


if __name__ == "__main__":
    unittest.main()
