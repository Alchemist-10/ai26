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
import mfa as mfa_tools
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
        case_ids = {"analyst": ["CASE-2026-01"], "viewer": ["CASE-55"]}.get(role, [])
        return self.auth.create_user(username, "Correct-Horse-Battery-Staple-26", role, case_ids=case_ids)

    def login(self, username="admin"):
        response = self.client.post("/api/auth/login", json={"username": username, "password": "Correct-Horse-Battery-Staple-26"})
        if response.status_code == 200:
            self.csrf = response.json()["csrf_token"]
        return response

    def csrf_headers(self):
        return {CSRF_HEADER: self.csrf}

    def test_current_schema_bootstrap_is_persistent_and_never_resets_password(self):
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
                self.assertEqual(repository.schema_version, 10)
                self.assertEqual(repository.db.execute("PRAGMA user_version").fetchone()[0], 10)
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
        wrong_case = self.client.get("/api/events", headers={**headers, "X-AI26-Case-ID": "CASE-OTHER"})
        self.assertEqual(wrong_case.status_code, 403)
        self.assertIn("not assigned", wrong_case.json()["error"]["message"])
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

    def test_authenticated_alert_review_uses_session_identity(self):
        self.create()
        self.login()
        alert_id = "auth-review-alert"
        self.repo.put_alert({"alert_id": alert_id, "ts": time.time(), "type": "watchlist match", "state": "open"})
        response = self.client.post(f"/api/alerts/{alert_id}/review", json={
            "state": "reviewed", "reviewer": "Impersonated Name", "note": "Checked evidence"
        }, headers={**self.csrf_headers(), "X-AI26-Case-ID": "CASE-2026-01", "X-AI26-Purpose": "investigation"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reviewer"], "admin")
        self.assertTrue(response.json()["reviewer_authenticated"])
        stored = self.repo.alerts()[0]["review"][0]
        self.assertEqual(stored["reviewer"], "admin")
        self.assertTrue(stored["reviewer_authenticated"])
        self.assertEqual(self.repo.verify_audit_chain()["status"], "valid")

    def test_prometheus_metrics_requires_admin_when_auth_is_enabled(self):
        self.create("analyst_one", "analyst")
        self.assertEqual(self.login("analyst_one").status_code, 200)
        self.assertEqual(self.client.get("/api/metrics").status_code, 403)
        self.create()
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/metrics").status_code, 200)

    def test_viewer_cannot_query_or_mutate_but_health_stays_public(self):
        self.create("viewer_one", "viewer")
        self.assertEqual(self.login("viewer_one").status_code, 200)
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["inference_branches"],
                         {"vehicle_detection_enabled": True, "plate_recognition_enabled": True})
        self.assertEqual(self.client.get("/api/cameras").status_code, 200)
        self.assertEqual(self.client.get("/api/events", headers={"X-AI26-Case-ID":"CASE-55","X-AI26-Purpose":"system_test"}).status_code, 403)
        self.assertEqual(self.client.get("/api/camera-pair-constraints").status_code, 403)

    def test_user_management_and_last_admin_protection(self):
        self.create()
        self.assertEqual(self.login().status_code, 200)
        created = self.client.post("/api/auth/users", json={
            "username": "operator_one", "password": "Operator-Correct-Horse-2026", "role": "operator",
            "case_ids": ["CASE-2026-02"],
        }, headers=self.csrf_headers())
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["role"], "operator")
        self.assertEqual(created.json()["case_ids"], ["CASE-2026-02"])
        operator_client = TestClient(main.app, base_url="https://testserver")
        self.assertEqual(operator_client.post("/api/auth/login", json={
            "username": "operator_one", "password": "Operator-Correct-Horse-2026",
        }).status_code, 200)
        last_admin = self.client.patch("/api/auth/users/admin", json={"disabled": True}, headers=self.csrf_headers())
        self.assertEqual(last_admin.status_code, 409)
        case_change = self.client.patch("/api/auth/users/operator_one", json={"case_ids": ["CASE-2026-03"]}, headers=self.csrf_headers())
        self.assertEqual(case_change.status_code, 200)
        self.assertEqual(self.auth.case_ids("operator_one"), ["CASE-2026-03"])
        self.assertEqual(operator_client.get("/api/auth/me").status_code, 401)
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
        with self.assertRaises(AuthenticationError):
            self.auth.create_user("user_one", "Correct-Horse-Battery-Staple-26", "analyst", case_ids=["*"])
        malformed = self.client.post("/api/auth/login", json={"username": "x", "password": "no"})
        self.assertEqual(malformed.status_code, 422)
        invalid = self.client.post("/api/auth/login", json={"username": "admin", "password": "Wrong-Correct-Horse-2026"})
        self.assertEqual(invalid.status_code, 401)

    def test_enrollment_login_recovery_use_and_disable(self):
        key_file = Path(self.folder.name) / "mfa.key"
        key_file.write_bytes(b"m" * 32); key_file.chmod(0o400)
        with patch.dict(os.environ, {"AI26_AUTH_MFA_KEY_FILE": str(key_file)}):
            self.create()
            with TestClient(main.app, base_url="https://testserver") as owner:
                signed = owner.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26"})
                csrf = signed.json()["csrf_token"]
                headers = {CSRF_HEADER: csrf}
                self.assertFalse(owner.get("/api/auth/mfa").json()["enabled"])
                setup = owner.post("/api/auth/mfa/setup", headers=headers)
                self.assertEqual(setup.status_code, 200)
                secret = setup.json()["secret"]
                confirmation = owner.post("/api/auth/mfa/enable", json={"code": mfa_tools.code_at(secret)}, headers=headers)
                self.assertEqual(confirmation.status_code, 200)
                recovery = confirmation.json()["recovery_codes"][0]
                self.assertEqual(len(confirmation.json()["recovery_codes"]), 10)
                encrypted = self.repo.db.execute("SELECT secret_ciphertext,recovery_hashes,enabled FROM user_mfa WHERE username='admin'").fetchone()
                self.assertTrue(encrypted["enabled"])
                self.assertNotIn(secret.encode(), bytes(encrypted["secret_ciphertext"]))
                self.assertNotIn(recovery, encrypted["recovery_hashes"])

                no_factor = TestClient(main.app, base_url="https://testserver")
                self.assertEqual(no_factor.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26"}).json()["error"]["message"], "MFA_CODE_REQUIRED")
                totp_login = TestClient(main.app, base_url="https://testserver")
                accepted = totp_login.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":mfa_tools.code_at(secret)})
                self.assertEqual(accepted.status_code, 200)
                with patch.dict(os.environ, {"AI26_AUTH_ENABLED":"1"}, clear=True):
                    unavailable = TestClient(main.app, base_url="https://testserver")
                    response = unavailable.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":mfa_tools.code_at(secret)})
                    self.assertEqual(response.status_code, 503)
                    self.assertIn("MFA cannot be verified", response.json()["error"]["message"])
                first_recovery = TestClient(main.app, base_url="https://testserver")
                self.assertEqual(first_recovery.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":recovery}).status_code, 200)
                reuse = TestClient(main.app, base_url="https://testserver")
                self.assertEqual(reuse.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":recovery}).status_code, 401)

                disabled = owner.post("/api/auth/mfa/disable", json={"password":"Correct-Horse-Battery-Staple-26","code":mfa_tools.code_at(secret)}, headers=headers)
                self.assertEqual(disabled.status_code, 200)
                self.assertFalse(owner.get("/api/auth/mfa").json()["enabled"])
                setup_again = owner.post("/api/auth/mfa/setup", headers=headers).json()
                confirmed_again = owner.post("/api/auth/mfa/enable", json={"code":mfa_tools.code_at(setup_again["secret"])}, headers=headers)
                self.assertEqual(confirmed_again.status_code, 200)
                reset = owner.delete("/api/auth/users/admin/mfa", headers=headers)
                self.assertEqual(reset.status_code, 200)
                self.assertEqual(owner.get("/api/auth/me").status_code, 401)
                self.assertIsNone(self.repo.db.execute("SELECT 1 FROM user_mfa WHERE username='admin'").fetchone())

    def test_mfa_key_permissions_and_totp_rfc6238_vector(self):
        key_file = Path(self.folder.name) / "mfa.key"
        key_file.write_bytes(b"m" * 32); key_file.chmod(0o644)
        with patch.dict(os.environ, {"AI26_AUTH_MFA_KEY_FILE": str(key_file)}):
            with self.assertRaisesRegex(RuntimeError, "group or other"):
                mfa_tools.encrypt_secret(mfa_tools.create_secret())
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(mfa_tools.code_at(secret, 59), "287082")
        self.assertTrue(mfa_tools.verify_totp(secret, "287082", 59))


if __name__ == "__main__":
    unittest.main()
