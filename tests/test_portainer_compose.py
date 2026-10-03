"""Portainer requires an explicit key, with no .env or manual model paths."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yaml"


class PortainerComposeContract(unittest.TestCase):
    def render(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ASR_")}
        env["ASR_API_KEY"] = "compose-contract-test-only"
        result = subprocess.run(
            ["docker", "compose", "--env-file", "/dev/null", "-f", str(COMPOSE), "config", "--format", "json"],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_stack_has_published_images_and_only_key_interpolation(self):
        self.assertEqual(COMPOSE.read_text().count("${"), 1)
        data = self.render()
        services = data["services"]
        self.assertEqual(set(services), {"engine", "gateway"})
        self.assertEqual(services["engine"]["image"], "chmodmasx/nemotron-asr-engine:0.1.0-cuda")
        self.assertEqual(services["gateway"]["image"], "chmodmasx/nemotron-asr-gateway:0.4.0")
        for service in services.values():
            self.assertNotIn("build", service)
        self.assertEqual(services["engine"]["depends_on"]["gateway"]["condition"], "service_healthy")
        self.assertNotIn("depends_on", services["gateway"])
        self.assertIn("socket.create_connection", " ".join(services["gateway"]["healthcheck"]["test"]))

    def test_missing_or_empty_key_rejects_deployment(self):
        for value in (None, ""):
            with self.subTest(value=value):
                env = {k: v for k, v in os.environ.items() if not k.startswith("ASR_")}
                if value is not None:
                    env["ASR_API_KEY"] = value
                result = subprocess.run(
                    ["docker", "compose", "--env-file", "/dev/null", "-f", str(COMPOSE), "config", "--quiet"],
                    cwd=ROOT, env=env, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ASR_API_KEY", result.stderr)

    def test_development_compose_also_needs_no_env(self):
        dev = ROOT / "compose.dev.yaml"
        self.assertNotIn("${", dev.read_text())
        env = {k: v for k, v in os.environ.items() if not k.startswith("ASR_")}
        result = subprocess.run(
            ["docker", "compose", "--env-file", "/dev/null", "-f", str(dev), "config", "--format", "json"],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)["services"]), {"engine", "gateway"})

    def test_model_and_key_are_persistent_but_not_published(self):
        data = self.render()
        services = data["services"]
        self.assertEqual(set(data["volumes"]), {"model", "auth"})
        for name in ("model", "auth"):
            mount = next(volume for volume in services["gateway"]["volumes"] if volume["source"] == name)
            self.assertFalse(mount.get("read_only", False))
        engine_model = next(volume for volume in services["engine"]["volumes"] if volume["target"] == "/models")
        self.assertTrue(engine_model["read_only"])
        self.assertEqual(services["gateway"]["user"], "0:0")
        self.assertEqual(services["gateway"]["environment"]["ASR_API_KEY"], "compose-contract-test-only")
        self.assertNotIn("ASR_API_KEY", services["engine"].get("environment", {}))
        self.assertNotIn("ports", services["engine"])
        self.assertEqual(services["engine"]["gpus"], [{"count": -1}])
        self.assertEqual(set(services["engine"]["networks"]), {"internal"})
        self.assertEqual(set(services["gateway"]["networks"]), {"internal", "public"})
        self.assertEqual(services["gateway"]["ports"][0]["host_ip"], "0.0.0.0")
        self.assertEqual(services["gateway"]["ports"][0]["published"], "18090")
        self.assertEqual({p.name for p in ROOT.glob("compose*.yaml")}, {"compose.yaml", "compose.dev.yaml"})


if __name__ == "__main__":
    unittest.main()
