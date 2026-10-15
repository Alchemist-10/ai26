import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from report_signing import EvidenceSigningError, generate_key_pair, sign_report, verify_report
from repository import canonical_json


class EvidenceSigning(unittest.TestCase):
    def test_generate_sign_and_verify_with_out_of_band_public_key(self):
        with tempfile.TemporaryDirectory() as folder:
            private = Path(folder) / "signing-private.pem"
            public = Path(folder) / "trusted-public.pem"
            fingerprint = generate_key_pair(private, public)
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            self.assertEqual(public.stat().st_mode & 0o777, 0o644)
            unsigned = {"report_id": "EVD-TEST", "version": 5, "result": {"count": 2}, "signature": None}
            with patch.dict(os.environ, {"AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE": str(private)}):
                unsigned["signature"] = sign_report(unsigned)
            unsigned["package_hash"] = hashlib.sha256(canonical_json(unsigned).encode()).hexdigest()
            self.assertEqual(unsigned["signature"]["key_fingerprint_sha256"], fingerprint)
            self.assertEqual(verify_report(unsigned, public)["status"], "valid")

            tampered = {**unsigned, "result": {"count": 3}}
            with self.assertRaisesRegex(EvidenceSigningError, "package hash does not match"):
                verify_report(tampered, public)
            tampered["package_hash"] = hashlib.sha256(
                canonical_json({key: value for key, value in tampered.items() if key != "package_hash"}).encode()
            ).hexdigest()
            with self.assertRaisesRegex(EvidenceSigningError, "signature verification failed"):
                verify_report(tampered, public)

            renamed = {**unsigned, "signature": {**unsigned["signature"], "key_id": "another-key"}}
            renamed["package_hash"] = hashlib.sha256(
                canonical_json({key: value for key, value in renamed.items() if key != "package_hash"}).encode()
            ).hexdigest()
            with self.assertRaisesRegex(EvidenceSigningError, "signature verification failed"):
                verify_report(renamed, public)

    def test_public_key_fingerprint_is_trusted_out_of_band(self):
        with tempfile.TemporaryDirectory() as folder:
            first_private, first_public = Path(folder) / "first.pem", Path(folder) / "first.pub.pem"
            second_private, second_public = Path(folder) / "second.pem", Path(folder) / "second.pub.pem"
            generate_key_pair(first_private, first_public)
            generate_key_pair(second_private, second_public)
            report = {"report_id": "EVD-TEST", "version": 5, "signature": None}
            with patch.dict(os.environ, {"AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE": str(first_private)}):
                report["signature"] = sign_report(report)
            report["package_hash"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
            with self.assertRaisesRegex(EvidenceSigningError, "No trusted public key fingerprint"):
                verify_report(report, second_public)

    def test_trusted_key_set_preserves_verification_across_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old_private, old_public = root / "old.pem", root / "old.pub.pem"
            new_private, new_public = root / "new.pem", root / "new.pub.pem"
            generate_key_pair(old_private, old_public)
            generate_key_pair(new_private, new_public)

            def report_for(private, report_id):
                report = {"report_id": report_id, "version": 5, "signature": None}
                with patch.dict(os.environ, {"AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE": str(private)}):
                    report["signature"] = sign_report(report)
                report["package_hash"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
                return report

            old_report = report_for(old_private, "EVD-OLD")
            new_report = report_for(new_private, "EVD-NEW")
            trusted = [old_public, new_public]
            self.assertEqual(verify_report(old_report, trusted)["status"], "valid")
            self.assertEqual(verify_report(new_report, trusted)["status"], "valid")
            with self.assertRaisesRegex(EvidenceSigningError, "No trusted public key"):
                verify_report(old_report, [new_public])

    def test_private_key_permissions_and_key_generation_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            private, public = Path(folder) / "private.pem", Path(folder) / "public.pem"
            public.write_text("preserve this trusted key")
            with self.assertRaises(FileExistsError):
                generate_key_pair(private, public)
            self.assertFalse(private.exists())
            self.assertEqual(public.read_text(), "preserve this trusted key")

            generate_key_pair(private, Path(folder) / "second-public.pem")
            private.chmod(0o644)
            with patch.dict(os.environ, {"AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE": str(private)}):
                with self.assertRaisesRegex(EvidenceSigningError, "must not grant group or other access"):
                    sign_report({"report_id": "EVD-TEST"})

    def test_signing_is_optional_only_when_key_is_unconfigured(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(sign_report({"report_id": "EVD-TEST"}))

    def test_cli_generates_keys_and_verifies_exported_manifest(self):
        script = Path(__file__).resolve().parents[1] / "backend" / "report_signing.py"
        with tempfile.TemporaryDirectory() as folder:
            private, public, report_path = (Path(folder) / name for name in ("private.pem", "public.pem", "report.json"))
            generated = subprocess.run(
                [sys.executable, str(script), "generate", "--private-key", str(private), "--public-key", str(public)],
                check=True, capture_output=True, text=True,
            )
            self.assertIn("public-key SHA-256", generated.stdout)
            report = {"report_id": "EVD-CLI-TEST", "version": 5, "value": 7, "signature": None}
            with patch.dict(os.environ, {"AI26_EVIDENCE_SIGNING_PRIVATE_KEY_FILE": str(private)}):
                report["signature"] = sign_report(report)
            report["package_hash"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
            report_path.write_text(json.dumps(report))
            verified = subprocess.run(
                [sys.executable, str(script), "verify", "--report", str(report_path), "--public-key", str(public)],
                check=True, capture_output=True, text=True,
            )
            self.assertIn("VALID report=EVD-CLI-TEST", verified.stdout)


if __name__ == "__main__":
    unittest.main()
