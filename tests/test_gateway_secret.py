"""Gateway image reads its per-install key from a Docker volume, never from Compose."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

IMAGE = os.getenv("GATEWAY_TEST_IMAGE", "nemotron-asr-gateway:0.3.0")


class GatewaySecretContract(unittest.TestCase):
    def run_container(self, key_path):
        return subprocess.run([
            "docker", "run", "--rm", "--network", "none",
            "--env", "ASR_API_KEY=wrong-inline-value",
            "--env", "ASR_API_KEY_FILE=/run/asr-auth/api_key",
            "--mount", f"type=bind,source={key_path},target=/run/asr-auth/api_key,readonly",
            "--entrypoint", "python", IMAGE,
            "-c", "import proxy; assert proxy.API_KEY == 'test-file-secret', 'key file did not override inline value'",
        ], capture_output=True, text=True, timeout=25)

    def test_file_secret_overrides_inline_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).chmod(0o755)  # dummy test secret readable by the container's unprivileged user
            key = Path(tmp) / "api_key"
            key.write_text("test-file-secret\n")
            key.chmod(0o644)
            result = self.run_container(key)
            self.assertEqual(result.returncode, 0, result.stderr)

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
