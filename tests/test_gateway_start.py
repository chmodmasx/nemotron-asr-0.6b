"""The persistent gateway initializes volumes before launching its web process."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))


class GatewayLauncherContract(unittest.TestCase):
    def test_gateway_image_starts_through_launcher(self):
        dockerfile = (ROOT / "gateway" / "Dockerfile").read_text()
        self.assertIn("COPY proxy.py bootstrap.py start.py", dockerfile)
        self.assertIn('CMD ["python", "/srv/app/start.py"]', dockerfile)

    def test_verified_model_and_key_exist_before_proxy_exec(self):
        import start  # the new persistent-service entrypoint
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.gguf"
            fixture.write_bytes(b"small verified model fixture")
            model = root / "model" / "nemotron.gguf"
            key = root / "auth" / "api_key"
            env = {
                "ASR_BOOTSTRAP_MODEL_URL": fixture.as_uri(),
                "ASR_BOOTSTRAP_SHA256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                "ASR_BOOTSTRAP_MODEL_PATH": str(model),
                "ASR_BOOTSTRAP_KEY_PATH": str(key),
                "ASR_BOOTSTRAP_UID": str(os.getuid()),
                "ASR_BOOTSTRAP_GID": str(os.getgid()),
            }
            with patch.dict(os.environ, env), patch.object(start.os, "execv") as replacement:
                start.main()
                replacement.assert_called_once_with(sys.executable, [sys.executable, "/srv/app/proxy.py"])
                self.assertEqual(model.read_bytes(), fixture.read_bytes())
                self.assertTrue(key.read_text().strip())


if __name__ == "__main__":
    unittest.main()
