"""Black-box bootstrap tests with a local file:// fixture (no network or GPU)."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "gateway" / "bootstrap.py"


class BootstrapContract(unittest.TestCase):
    def setup_fixture(self, directory):
        root = Path(directory)
        source = root / "sample.gguf"
        source.write_bytes(b"small local model fixture for bootstrap\n")
        destination = root / "model" / "nemotron-3.5-asr-streaming-0.6b.q8_0.gguf"
        key = root / "auth" / "api_key"
        env = os.environ.copy()
        env.update({
            "ASR_BOOTSTRAP_MODEL_URL": source.as_uri(),
            "ASR_BOOTSTRAP_SHA256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "ASR_BOOTSTRAP_MODEL_PATH": str(destination),
            "ASR_BOOTSTRAP_KEY_PATH": str(key),
            "ASR_BOOTSTRAP_UID": str(os.getuid()),
            "ASR_BOOTSTRAP_GID": str(os.getgid()),
        })
        return source, destination, key, env

    def invoke(self, env):
        return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=15)

    def test_downloads_verified_model_and_generates_persistent_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination, key, env = self.setup_fixture(directory)
            first = self.invoke(env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertGreater(len(key.read_text().strip()), 32)
            self.assertEqual(key.stat().st_mode & 0o777, 0o640)
            original = key.read_bytes()
            source.write_bytes(b"changed; should not be downloaded when cached")
            second = self.invoke(env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(key.read_bytes(), original)
            self.assertEqual(destination.read_bytes(), b"small local model fixture for bootstrap\n")
            self.assertNotIn(original.decode(), first.stdout + first.stderr + second.stdout + second.stderr)

    def test_existing_key_is_kept_when_permissions_are_hardened(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, key, env = self.setup_fixture(directory)
            key.parent.mkdir()
            key.write_text("old-stable-key\n")
            key.chmod(0o600)
            result = self.invoke(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(key.read_text(), "old-stable-key\n")
            self.assertEqual(key.stat().st_mode & 0o777, 0o640)

    def test_existing_bad_model_is_refused_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            _, destination, key, env = self.setup_fixture(directory)
            destination.parent.mkdir()
            destination.write_bytes(b"tampered")
            result = self.invoke(env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Existing model checksum mismatch", result.stderr)
            self.assertEqual(destination.read_bytes(), b"tampered")
            self.assertFalse(key.exists())

    def test_download_with_wrong_hash_does_not_become_live_model(self):
        with tempfile.TemporaryDirectory() as directory:
            _, destination, key, env = self.setup_fixture(directory)
            env["ASR_BOOTSTRAP_SHA256"] = "0" * 64
            result = self.invoke(env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Downloaded model checksum mismatch", result.stderr)
            self.assertFalse(destination.exists())
            self.assertFalse(key.exists())


if __name__ == "__main__":
    unittest.main()
