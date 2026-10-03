"""Environment keys override stored keys without rewriting persistent volumes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

IMAGE = os.getenv("GATEWAY_TEST_IMAGE", "nemotron-asr-gateway:0.4.0")


class GatewaySecretContract(unittest.TestCase):
    def run_container(self, key_path, env_value=None, expected="test-file-secret"):
        args = ["docker", "run", "--rm", "--network", "none"]
        if env_value is not None:
            args += ["--env", "ASR_API_KEY=" + env_value]
        args += [
            "--env", "ASR_API_KEY_FILE=/run/asr-auth/api_key",
            "--mount", f"type=bind,source={key_path},target=/run/asr-auth/api_key,readonly",
            "--entrypoint", "python", IMAGE,
            "-c", f"import proxy; assert proxy.API_KEY == {expected!r}, 'unexpected effective key'",
        ]
        return subprocess.run(args, capture_output=True, text=True, timeout=25)

    def test_environment_key_overrides_stored_key_without_changing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).chmod(0o755)
            key = Path(tmp) / "api_key"
            key.write_text("test-file-secret\n")
            key.chmod(0o644)
            result = self.run_container(key, "test-env-secret", "test-env-secret")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(key.read_text(), "test-file-secret\n")

    def test_stored_key_remains_fallback_without_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).chmod(0o755)
            key = Path(tmp) / "api_key"
            key.write_text("test-file-secret\n")
            key.chmod(0o644)
            result = self.run_container(key)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_environment_never_falls_back_to_stored_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).chmod(0o755)
            key = Path(tmp) / "api_key"
            key.write_text("test-file-secret\n")
            key.chmod(0o644)
            for value in ("", " ", "bad key", "bad\nkey", "bad\tkey", "bad\x7fkey", "clavé"):
                with self.subTest(value=value):
                    result = self.run_container(key, value)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("ASR_API_KEY must be", result.stderr)
                    self.assertEqual(key.read_text(), "test-file-secret\n")

    def test_empty_key_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).chmod(0o755)
            key = Path(tmp) / "api_key"
            key.write_text("")
            key.chmod(0o644)
            result = self.run_container(key)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("API key file is empty", result.stderr)


if __name__ == "__main__":
    unittest.main()
