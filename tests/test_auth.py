import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
import main
import events
from auth import AuthService, AuthenticationError, CSRF_HEADER, MAX_AUTH_ATTEMPTS, SESSION_COOKIE
import auth as auth_module
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
                self.assertEqual(repository.schema_version, 13)
                self.assertEqual(repository.db.execute("PRAGMA user_version").fetchone()[0], 13)
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
        self.assertEqual(self.client.get("/api/traffic/baselines?days=28").status_code, 422)
        baselines=self.client.get("/api/traffic/baselines?days=28",headers=headers)
        self.assertEqual(baselines.status_code,200)
        self.assertEqual(baselines.json()['time_basis'],'capture_arrival_clock')

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

    def test_active_escalations_are_bound_to_case_and_other_case_cannot_resolve(self):
        password="Correct-Horse-Battery-Staple-26"
        self.auth.create_user("operator_one",password,"operator",case_ids=["CASE-ALPHA"])
        self.auth.create_user("operator_two",password,"operator",case_ids=["CASE-BRAVO"])
        alert_id="case-scoped-escalation"
        self.repo.put_alert({"alert_id":alert_id,"ts":time.time(),"type":"watchlist match","summary":"Local fixture"})

        login_one=self.client.post("/api/auth/login",json={"username":"operator_one","password":password})
        self.assertEqual(login_one.status_code,200)
        headers_one={
            CSRF_HEADER:login_one.json()["csrf_token"],
            "X-AI26-Case-ID":"CASE-ALPHA","X-AI26-Purpose":"incident_response",
        }
        escalated=self.client.post(f"/api/alerts/{alert_id}/review",json={
            "state":"escalated","reviewer":"Claimed Operator","escalation_target":"Duty desk","note":"Needs follow-up",
        },headers=headers_one)
        self.assertEqual(escalated.status_code,200)
        self.assertEqual(escalated.json()["case_id"],"CASE-ALPHA")
        queue_one=self.client.get("/api/alerts/escalations",headers={k:v for k,v in headers_one.items() if k!=CSRF_HEADER})
        self.assertEqual([item["alert_id"] for item in queue_one.json()["items"]],[alert_id])

        other=TestClient(main.app,base_url="https://testserver")
        login_two=other.post("/api/auth/login",json={"username":"operator_two","password":password})
        self.assertEqual(login_two.status_code,200)
        headers_two={
            CSRF_HEADER:login_two.json()["csrf_token"],
            "X-AI26-Case-ID":"CASE-BRAVO","X-AI26-Purpose":"incident_response",
        }
        queue_two=other.get("/api/alerts/escalations",headers={k:v for k,v in headers_two.items() if k!=CSRF_HEADER})
        self.assertEqual(queue_two.status_code,200)
        self.assertEqual(queue_two.json()["items"],[])
        compatibility_view=other.get("/api/alerts?include_escalated=true",headers={k:v for k,v in headers_two.items() if k!=CSRF_HEADER})
        self.assertEqual(compatibility_view.status_code,200)
        self.assertNotIn(alert_id,[item["alert_id"] for item in compatibility_view.json()])
        cross_case=other.post(f"/api/alerts/{alert_id}/review",json={
            "state":"acknowledged","reviewer":"Operator Two","note":"Cross-case attempt",
        },headers=headers_two)
        self.assertEqual(cross_case.status_code,404)
        self.assertEqual(self.client.get("/api/alerts/escalations",headers={k:v for k,v in headers_one.items() if k!=CSRF_HEADER}).json()["items"][0]["case_id"],"CASE-ALPHA")
        self.assertEqual(self.repo.verify_audit_chain()["status"],"valid")
        other.close()

    def test_self_service_password_change_checks_current_password_and_revokes_sessions(self):
        self.create()
        self.assertEqual(self.login().status_code, 200)
        other=TestClient(main.app,base_url="https://testserver")
        self.addCleanup(other.close)
        self.assertEqual(other.post("/api/auth/login",json={
            "username":"admin","password":"Correct-Horse-Battery-Staple-26"}).status_code,200)

        payload={"current_password":"Correct-Horse-Battery-Staple-26",
                 "new_password":"New-Correct-Horse-Battery-2026"}
        self.assertEqual(self.client.post("/api/auth/me/password",json=payload).status_code,403)
        wrong={**payload,"current_password":"Wrong-Correct-Horse-Battery-26"}
        self.assertEqual(self.client.post("/api/auth/me/password",json=wrong,headers=self.csrf_headers()).status_code,422)
        same={**payload,"new_password":payload["current_password"]}
        self.assertEqual(self.client.post("/api/auth/me/password",json=same,headers=self.csrf_headers()).status_code,422)

        changed=self.client.post("/api/auth/me/password",json=payload,headers=self.csrf_headers())
        self.assertEqual(changed.status_code,200)
        self.assertEqual(changed.json(),{"password_changed":True,"sessions_revoked":True})
        self.assertEqual(self.client.get("/api/auth/me").status_code,401)
        self.assertEqual(other.get("/api/auth/me").status_code,401)
        self.assertEqual(other.post("/api/auth/login",json={
            "username":"admin","password":"Correct-Horse-Battery-Staple-26"}).status_code,401)
        self.assertEqual(self.login().status_code,401)
        self.assertEqual(self.client.post("/api/auth/login",json={
            "username":"admin","password":payload["new_password"]}).status_code,200)
        self.assertEqual(self.repo.verify_audit_chain()["status"],"valid")
        audit=self.repo.db.execute("SELECT action,data FROM audit WHERE action='auth_password_changed'").fetchone()
        self.assertEqual(audit["action"],"auth_password_changed")
        self.assertEqual(json.loads(audit["data"]),{"sessions_revoked":True})

    def _enroll_test_mfa(self, username, secret, recovery_codes):
        hashes = json.dumps([mfa_tools.recovery_hash(code) for code in recovery_codes], separators=(",", ":"))
        with self.repo.lock, self.repo.db:
            self.repo.db.execute("INSERT INTO user_mfa(username,secret_ciphertext,enabled,recovery_hashes,updated_at,expires_at) VALUES(?,?,?,?,?,?)",
                                 (username,mfa_tools.encrypt_secret(secret),1,hashes,time.time(),0))

    def test_mfa_recovery_resets_password_consumes_code_and_revokes_sessions(self):
        key_path = Path(self.folder.name) / "mfa.key"
        key_path.write_bytes(b"m" * 32)
        key_path.chmod(0o600)
        codes = ["ABCDEF0123456789", "1234567890ABCDEF", "FEDCBA9876543210", "0123456789ABCDEF", "89ABCDEF01234567", "76543210FEDCBA98"]
        secret = mfa_tools.create_secret()
        self.create()
        with patch.dict(os.environ, {"AI26_AUTH_MFA_KEY_FILE": str(key_path)}):
            self._enroll_test_mfa("admin", secret, codes)
            first = TestClient(main.app, base_url="https://testserver")
            second = TestClient(main.app, base_url="https://testserver")
            self.addCleanup(first.close)
            self.addCleanup(second.close)
            self.assertEqual(first.post("/api/auth/login", json={
                "username":"admin", "password":"Correct-Horse-Battery-Staple-26",
                "mfa_code":codes[0],
            }).status_code, 200)
            self.assertEqual(second.post("/api/auth/login", json={
                "username":"admin", "password":"Correct-Horse-Battery-Staple-26",
                "mfa_code":codes[1],
            }).status_code, 200)

            payload={"username":"admin", "new_password":"Recovered-Correct-Horse-2026", "code":codes[2]}
            response=first.post("/api/auth/password-recovery", json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"recovery_requested":True})
            self.assertEqual(first.get("/api/auth/me").status_code, 401)
            self.assertEqual(second.get("/api/auth/me").status_code, 401)
            # The authenticator counter remains available after recovery-code use,
            # then cannot be replayed for another login in the same time step.
            self.assertEqual(self.client.post("/api/auth/login", json={
                "username":"admin", "password":payload["new_password"], "mfa_code":mfa_tools.code_at(secret),
            }).status_code, 200)
            self.assertEqual(self.client.post("/api/auth/login", json={
                "username":"admin", "password":payload["new_password"], "mfa_code":mfa_tools.code_at(secret),
            }).status_code, 401)
            self.assertEqual(self.client.post("/api/auth/login", json={
                "username":"admin", "password":payload["new_password"], "mfa_code":codes[3],
            }).status_code, 200)
            # The same recovery code cannot authorize another password change.
            again={**payload, "new_password":"Another-Recovered-Horse-2026"}
            self.assertEqual(first.post("/api/auth/password-recovery", json=again).json(), {"recovery_requested":True})
            self.assertEqual(self.client.post("/api/auth/login", json={
                "username":"admin", "password":payload["new_password"], "mfa_code":codes[4],
            }).status_code, 200)
            self.assertEqual(self.repo.verify_audit_chain()["status"], "valid")
            self.assertEqual(self.repo.db.execute("SELECT count(*) FROM audit WHERE action='auth_password_recovered'").fetchone()[0], 1)
            # An authenticator TOTP can also reset the password and revokes the new session.
            totp_recovery={"username":"admin", "new_password":"TOTP-Recovered-Horse-2026",
                           "code":mfa_tools.code_at(secret, time.time()+30)}
            self.assertEqual(self.client.post("/api/auth/password-recovery", json=totp_recovery).json(), {"recovery_requested":True})
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
            self.assertEqual(self.client.post("/api/auth/login", json={
                "username":"admin", "password":totp_recovery["new_password"], "mfa_code":codes[5],
            }).status_code, 200)
            self.assertEqual(self.repo.db.execute("SELECT count(*) FROM audit WHERE action='auth_password_recovered'").fetchone()[0], 2)

    def test_password_recovery_does_not_disclose_account_or_mfa_state(self):
        key_path = Path(self.folder.name) / "mfa.key"
        key_path.write_bytes(b"r" * 32)
        key_path.chmod(0o600)
        self.create()
        self.auth.create_user("plain_user", "Plain-Correct-Horse-2026", "viewer")
        with patch.dict(os.environ, {"AI26_AUTH_MFA_KEY_FILE": str(key_path)}):
            payload={"new_password":"Another-Recovered-Horse-2026", "code":"not-a-code"}
            missing=self.client.post("/api/auth/password-recovery", json={**payload,"username":"missing_user"})
            no_mfa=self.client.post("/api/auth/password-recovery", json={**payload,"username":"plain_user"})
            self.assertEqual(missing.status_code, 200)
            self.assertEqual(no_mfa.status_code, 200)
            self.assertEqual(missing.json(), no_mfa.json())
            self.assertEqual(self.client.post("/api/auth/login", json={
                "username":"plain_user","password":"Plain-Correct-Horse-2026"}).status_code, 200)
            for _ in range(MAX_AUTH_ATTEMPTS):
                self.assertEqual(self.client.post("/api/auth/password-recovery", json={
                    **payload,"username":"missing_user"}).status_code, 200)
            limited=self.client.post("/api/auth/password-recovery", json={**payload,"username":"another_missing"})
            self.assertEqual(limited.status_code, 429)

    def test_prometheus_metrics_requires_admin_when_auth_is_enabled(self):
        self.create("analyst_one", "analyst")
        self.assertEqual(self.login("analyst_one").status_code, 200)
        self.assertEqual(self.client.get("/api/metrics").status_code, 403)
        self.create()
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/metrics").status_code, 200)

    def test_metrics_scraper_token_is_read_only_and_limited_to_metrics_route(self):
        token="a"*64
        token_file=Path(self.folder.name)/"metrics-token"
        token_file.write_text(token)
        with patch.dict(os.environ,{"AI26_METRICS_TOKEN_FILE":str(token_file)}):
            headers={"Authorization":f"Bearer {token}"}
            self.assertEqual(self.client.get("/api/metrics",headers=headers).status_code,200)
            self.assertEqual(self.client.get("/api/metrics",headers={"Authorization":"Bearer wrong"}).status_code,401)
            self.assertEqual(self.client.get("/api/events",headers=headers).status_code,401)
        token_file.write_text("too-short")
        with patch.dict(os.environ,{"AI26_METRICS_TOKEN_FILE":str(token_file)}):
            self.assertEqual(self.client.get("/api/metrics",headers={"Authorization":"Bearer too-short"}).status_code,401)

    def test_viewer_cannot_query_or_mutate_but_health_stays_public(self):
        self.create("viewer_one", "viewer")
        self.assertEqual(self.login("viewer_one").status_code, 200)
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["inference_branches"],
                         {"vehicle_detection_enabled": True, "plate_recognition_enabled": True})
        self.assertEqual(health.json()["vehicle_model_rollout"]["mode"], "stable_only")
        self.assertEqual(self.client.get("/api/cameras").status_code, 200)
        self.assertEqual(self.client.get("/api/events", headers={"X-AI26-Case-ID":"CASE-55","X-AI26-Purpose":"system_test"}).status_code, 403)
        self.assertEqual(self.client.get("/api/camera-pair-constraints").status_code, 403)
        self.assertEqual(self.client.get("/api/traffic/baselines",headers={
            "X-AI26-Case-ID":"CASE-55","X-AI26-Purpose":"system_test"}).status_code,403)

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
                                 [(client_hash, now)] * MAX_AUTH_ATTEMPTS)
        limited = self.login()
        self.assertEqual(limited.status_code, 429)
        self.repo.db.execute("DELETE FROM auth_login_failures")
        self.repo.db.commit()
        result = self.login()
        self.assertEqual(result.status_code, 200)
        token = self.client.cookies.get(SESSION_COOKIE)
        self.assertIsNotNone(self.auth.session(token))
        self.assertIsNone(self.auth.session(token, now + 9 * 60 * 60))

    def test_concurrent_login_attempts_reserve_the_ip_limit_atomically(self):
        address = "parallel-client"
        with patch.object(auth_module, "_derive", return_value=b"wrong-password-hash"):
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(
                    lambda _: self.auth.login("unknown_user", "not-the-password", address), range(12)
                ))
        reasons = [reason for _, reason in results]
        self.assertEqual(reasons.count("invalid"), MAX_AUTH_ATTEMPTS)
        self.assertEqual(reasons.count("limited"), 12 - MAX_AUTH_ATTEMPTS)
        address_hash=hashlib.sha256(address.encode()).hexdigest()
        self.assertEqual(self.repo.db.execute(
            "SELECT count(*) FROM auth_login_failures WHERE client_hash=?", (address_hash,)
        ).fetchone()[0], MAX_AUTH_ATTEMPTS)

    def test_concurrent_totp_replay_creates_at_most_one_session(self):
        key_path = Path(self.folder.name) / "mfa.key"
        key_path.write_bytes(b"t" * 32)
        key_path.chmod(0o600)
        secret = mfa_tools.create_secret()
        self.create()
        with patch.dict(os.environ, {"AI26_AUTH_MFA_KEY_FILE": str(key_path)}):
            self._enroll_test_mfa("admin", secret, [])
            now = float((int(time.time()) // 30) * 30 + 10)
            code = mfa_tools.code_at(secret, now)
            both_verified = threading.Barrier(2)
            thread_state = threading.local()
            match_counter = mfa_tools.matched_totp_counter

            def synchronize_first_match(value, submitted, timestamp):
                counter = match_counter(value, submitted, timestamp)
                if not getattr(thread_state, "matched", False):
                    thread_state.matched = True
                    both_verified.wait(timeout=5)
                return counter

            with patch.object(mfa_tools, "matched_totp_counter", side_effect=synchronize_first_match):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(
                        lambda _: self.auth.login("admin", "Correct-Horse-Battery-Staple-26",
                                                  "shared-mfa-client", now, code), range(2)
                    ))

        self.assertEqual(sum(result is not None for result, _ in results), 1)
        self.assertEqual([reason for result, reason in results if result is None], ["mfa_invalid"])
        self.assertEqual(self.repo.db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0], 1)
        self.assertEqual(self.repo.db.execute("SELECT count(*) FROM audit WHERE action='auth_login'").fetchone()[0], 1)

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
                replayed = totp_login.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":mfa_tools.code_at(secret)})
                self.assertEqual(replayed.status_code, 401)
                accepted = totp_login.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":confirmation.json()["recovery_codes"][0]})
                self.assertEqual(accepted.status_code, 200)
                with patch.dict(os.environ, {"AI26_AUTH_ENABLED":"1"}, clear=True):
                    unavailable = TestClient(main.app, base_url="https://testserver")
                    response = unavailable.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":mfa_tools.code_at(secret)})
                    self.assertEqual(response.status_code, 503)
                    self.assertIn("MFA cannot be verified", response.json()["error"]["message"])
                first_recovery = TestClient(main.app, base_url="https://testserver")
                recovery_code = confirmation.json()["recovery_codes"][1]
                self.assertEqual(first_recovery.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":recovery_code}).status_code, 200)
                reuse = TestClient(main.app, base_url="https://testserver")
                self.assertEqual(reuse.post("/api/auth/login", json={"username":"admin","password":"Correct-Horse-Battery-Staple-26","mfa_code":recovery_code}).status_code, 401)

                disabled = owner.post("/api/auth/mfa/disable", json={"password":"Correct-Horse-Battery-Staple-26","code":mfa_tools.code_at(secret,time.time()+30)}, headers=headers)
                self.assertEqual(disabled.status_code, 200, disabled.text)
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
        self.assertEqual(mfa_tools.matched_totp_counter(secret, "287082", 59), 1)


if __name__ == "__main__":
    unittest.main()
