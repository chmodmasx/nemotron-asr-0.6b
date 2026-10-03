"""Acceptance checks for a two-container running development stack."""
import json
from pathlib import Path
import subprocess
import unittest

from test_contract import compose_command

ROOT = Path(__file__).resolve().parents[1]
BASE = compose_command()


class GatewayRuntimeContract(unittest.TestCase):
    def test_exactly_two_created_containers(self):
        result = subprocess.run(BASE + ["ps", "-a", "--format", "json"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual({row["Service"] for row in rows}, {"engine", "gateway"})
        self.assertTrue(all(row["State"] == "running" for row in rows))

    def test_gateway_process_dropped_root_and_model_key_cannot_be_rewritten(self):
        script = '''
import os
from pathlib import Path
status = Path('/proc/1/status').read_text().splitlines()
uid = int(next(x for x in status if x.startswith('Uid:')).split()[1])
gid = int(next(x for x in status if x.startswith('Gid:')).split()[1])
assert (uid, gid) == (65532, 65532), (uid, gid)
key = Path('/run/asr-auth/api_key')
model = Path('/models/nemotron-3.5-asr-streaming-0.6b.q8_0.gguf')
assert (key.stat().st_uid, key.stat().st_gid, key.stat().st_mode & 0o777) == (0, 65532, 0o640)
assert model.is_file()
assert not os.access(key, os.W_OK) and not os.access(model, os.W_OK)
print('unprivileged gateway and persistent key/model permissions OK')
'''
        result = subprocess.run(
            BASE + ["exec", "-T", "--user", "65532:65532", "gateway", "python", "-c", script],
            cwd=ROOT, capture_output=True, text=True, timeout=25,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("permissions OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
