"""End-to-end authenticated PCM16LE WebSocket on the local development stack."""
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = '''
import asyncio
import json
import proxy
from aiohttp import ClientSession, WSMsgType

async def run():
    key = proxy.API_KEY
    async with ClientSession() as session:
        async with session.ws_connect(
            'http://127.0.0.1:8080/v1/audio/transcriptions/realtime',
            headers={'Authorization': 'Bearer ' + key}, heartbeat=30,
        ) as socket:
            created = await socket.receive_json(timeout=20)
            assert created.get('type') == 'session.created', created
            await socket.send_json({'type': 'session.update', 'session': {'language': 'es-US', 'sample_rate': 16000}})
            await socket.send_bytes(b'\\x00\\x00' * 16000)
            await socket.send_json({'type': 'input_audio_buffer.commit'})
            for _ in range(30):
                msg = await socket.receive(timeout=90)
                assert msg.type == WSMsgType.TEXT, msg.type
                event = json.loads(msg.data)
                assert event.get('type') != 'error', event
                if event.get('type') == 'conversation.item.input_audio_transcription.completed':
                    assert isinstance(event.get('transcript'), str), event
                    print('Authenticated WebSocket final event OK')
                    return
            raise AssertionError('No transcription completion received')

asyncio.run(run())
'''


class StreamingContract(unittest.TestCase):
    def test_authenticated_pcm_stream_yields_final_event(self):
        result = subprocess.run(
            ["docker", "compose", "--env-file", "/dev/null", "-f", str(ROOT / "compose.dev.yaml"),
             "exec", "-T", "gateway", "python", "-c", SCRIPT],
            cwd=ROOT, capture_output=True, text=True, timeout=150,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Authenticated WebSocket final event OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
