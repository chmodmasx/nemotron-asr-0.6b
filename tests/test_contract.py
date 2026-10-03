"""Black-box checks for the public ASR gateway (stdlib only)."""
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("ASR_BASE_URL", "http://127.0.0.1:18091").rstrip("/")


@lru_cache(maxsize=1)
def api_key():
    """Read the generated test key without logging it or needing a .env file."""
    compose = os.getenv("ASR_TEST_COMPOSE", str(ROOT / "compose.dev.yaml"))
    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "-f", compose,
         "exec", "-T", "gateway", "python", "-c",
         "from pathlib import Path; print(Path('/run/asr-auth/api_key').read_text().strip())"],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise AssertionError("Could not read generated key from test gateway: " + result.stderr)
    return result.stdout.strip()


def wav_bytes():
    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 8000)
    return data.getvalue()


def multipart(fields, filename, audio):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.extend((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode(), str(value).encode(), b"\r\n"))
    parts.extend((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(), audio, f"\r\n--{boundary}--\r\n".encode()))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class GatewayContract(unittest.TestCase):
    def fetch(self, path, method="GET", body=None, content_type=None, authorized=True):
        headers = {}
        if authorized:
            headers["Authorization"] = "Bearer " + api_key()
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as result:
                return result.status, result.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.read()

    def test_readiness_and_model_inventory(self):
        status, body = self.fetch("/ready", authorized=False)
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ready"])
        status, body = self.fetch("/v1/models")
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["data"])

    def test_api_requires_bearer(self):
        status, _ = self.fetch("/v1/models", authorized=False)
        self.assertEqual(status, 401)

    def test_wav_transcription_contract(self):
        body, content_type = multipart({"model": "default", "language": "es"}, "voice.wav", wav_bytes())
        status, response = self.fetch("/v1/audio/transcriptions", "POST", body, content_type)
        self.assertEqual(status, 200, response)
        self.assertIsInstance(json.loads(response)["text"], str)

    def test_ogg_opus_transcription_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.wav"
            target = Path(tmp) / "in.ogg"
            source.write_bytes(wav_bytes())
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), "-c:a", "libopus", str(target)], check=True)
            body, content_type = multipart({"model": "default"}, target.name, target.read_bytes())
            status, response = self.fetch("/v1/audio/transcriptions", "POST", body, content_type)
            self.assertEqual(status, 200, response)
            self.assertIsInstance(json.loads(response)["text"], str)

    def test_mp3_transcription_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.wav"
            target = Path(tmp) / "in.mp3"
            source.write_bytes(wav_bytes())
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), "-c:a", "libmp3lame", str(target)], check=True)
            body, content_type = multipart({"model": "default"}, target.name, target.read_bytes())
            status, response = self.fetch("/v1/audio/transcriptions", "POST", body, content_type)
            self.assertEqual(status, 200, response)
            self.assertIsInstance(json.loads(response)["text"], str)

    def test_invalid_audio_rejected(self):
        body, content_type = multipart({"model": "default"}, "invalid.bin", b"not a real audio file")
        status, _ = self.fetch("/v1/audio/transcriptions", "POST", body, content_type)
        self.assertEqual(status, 415)


if __name__ == "__main__":
    unittest.main()
