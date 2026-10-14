import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "checkpoint-audit.sh"


class AuditCheckpointScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.key = self.root / "private.pem"
        self.key.write_text("fixture")
        self.mount = self.root / "mounted"
        self.mount.mkdir()
        self.output = self.mount / "audit"
        self.capture = self.root / "docker-args"
        self._command("docker", f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{self.capture}'\n")
        self._command("date", "#!/bin/sh\nprintf '20261014T020000Z\\n'\n")

    def _command(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def _env(self, mountpoint_exit):
        self._command("mountpoint", f"#!/bin/sh\nexit {mountpoint_exit}\n")
        return {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "AI26_AUDIT_CHECKPOINT_PRIVATE_KEY_FILE": str(self.key),
            "AI26_AUDIT_CHECKPOINT_DIR": str(self.output),
            "AI26_AUDIT_CHECKPOINT_MOUNT": str(self.mount),
        }

    def test_unmounted_checkpoint_target_refuses_local_fallback(self):
        result = subprocess.run(["sh", str(SCRIPT)], env=self._env(1), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing local fallback", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.capture.exists())

    def test_mounted_target_runs_unique_timestamped_checkpoint_command(self):
        result = subprocess.run(["sh", str(SCRIPT)], env=self._env(0), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = self.capture.read_text().splitlines()
        self.assertIn("audit-checkpoint", arguments)
        self.assertIn("create", arguments)
        self.assertEqual(arguments[arguments.index("--output") + 1],
                         "/checkpoints/ai26-audit-20261014T020000Z.json")
        self.assertTrue(self.output.is_dir())


if __name__ == "__main__":
    unittest.main()
