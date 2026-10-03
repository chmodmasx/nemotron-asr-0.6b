"""OpenAI-style batch ASR adapter and transparent realtime PCM16 WebSocket gateway."""
import asyncio
import hmac
import json
import os
from pathlib import Path
import tempfile

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType, web

ENGINE = os.getenv("ASR_ENGINE_URL", "http://engine:8080").rstrip("/")


def load_api_key():
    # A user-selected key must take priority without rotating the fallback volume.
    if "ASR_API_KEY" in os.environ:
        key = os.environ["ASR_API_KEY"]
        if not key or any(char.isspace() or ord(char) < 33 or ord(char) > 126 for char in key):
            raise RuntimeError("ASR_API_KEY must be a nonempty printable ASCII token without whitespace")
        return key
    key_file = Path(os.getenv("ASR_API_KEY_FILE", "/run/asr-auth/api_key"))
    if os.getenv("ASR_API_KEY_FILE") or key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if not key:
            raise RuntimeError("API key file is empty")
        return key
    return os.environ["ASR_API_KEY"]  # no source available: fail closed


API_KEY = load_api_key()
DEFAULT_LANGUAGE = os.getenv("ASR_DEFAULT_LANGUAGE", "es-US")
MAX_INPUT = 64 * 1024 * 1024
MAX_WAV = 52 * 1024 * 1024
ALLOWED_FIELDS = {"model", "language", "response_format", "prompt", "automatic_punctuation", "verbatim", "profanity_filter", "diarization", "speech_contexts"}


def error(message, status):
    return web.json_response({"error": {"message": message, "type": "invalid_request_error" if status < 500 else "server_error"}}, status=status)


def authorized(request):
    bearer = request.headers.get("Authorization", "")
    token = bearer.removeprefix("Bearer ") if bearer.startswith("Bearer ") else request.query.get("api_key", "")
    return bool(API_KEY) and hmac.compare_digest(token, API_KEY)


def language(value):
    if not value or value.lower() == "es":
        return DEFAULT_LANGUAGE
    return value


async def http_proxy(request):
    if request.path not in ("/health", "/ready") and not authorized(request):
        return error("Authentication required", 401)
    try:
        async with request.app["client"].request(request.method, ENGINE + request.path, timeout=ClientTimeout(total=10)) as upstream:
            return web.Response(status=upstream.status, body=await upstream.read(), content_type=upstream.content_type)
    except (ClientError, asyncio.TimeoutError):
        return error("ASR engine unavailable", 502)


async def convert_audio(source, target):
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
        "-map", "0:a:0", "-vn", "-t", "900", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", "-f", "wav", str(target),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return False
    return proc.returncode == 0 and target.exists() and target.stat().st_size > 44


async def transcribe(request):
    if not authorized(request):
        return error("Authentication required", 401)
    if not request.content_type.startswith("multipart/"):
        return error("Expected multipart audio upload", 415)
    if request.content_length and request.content_length > MAX_INPUT:
        return error("Audio upload too large", 413)

    fields = {}
    try:
        with tempfile.TemporaryDirectory(prefix="asr-") as folder:
            source = Path(folder) / "source"
            target = Path(folder) / "converted.wav"
            reader = await request.multipart()
            received = False
            size = 0
            async for part in reader:
                if part.name == "file" and not received:
                    received = True
                    with source.open("wb") as output:
                        while chunk := await part.read_chunk(262144):
                            size += len(chunk)
                            if size > MAX_INPUT:
                                return error("Audio upload too large", 413)
                            output.write(chunk)
                elif part.name in ALLOWED_FIELDS:
                    value = await part.read(decode=True)
                    if len(value) > 8192:
                        return error("Form field too large", 413)
                    fields[part.name] = value.decode("utf-8", "replace")
                else:
                    await part.release()
            if not received or not size:
                return error("Missing audio file", 400)
            if not await convert_audio(source, target):
                return error("Unsupported or invalid audio", 415)
            if target.stat().st_size > MAX_WAV:
                return error("Converted audio too large", 413)
            fields["language"] = language(fields.get("language"))
            fields.setdefault("model", "default")
            from aiohttp import FormData
            form = FormData()
            for name, value in fields.items():
                form.add_field(name, value)
            with target.open("rb") as audio:
                form.add_field("file", audio, filename="audio.wav", content_type="audio/wav")
                try:
                    async with request.app["client"].post(
                        ENGINE + "/v1/audio/transcriptions", data=form, timeout=ClientTimeout(total=180)
                    ) as upstream:
                        content = await upstream.read()
                        return web.Response(status=upstream.status, body=content, content_type=upstream.content_type)
                except (ClientError, asyncio.TimeoutError):
                    return error("ASR engine unavailable", 502)
    except (ValueError, UnicodeError):
        return error("Invalid multipart audio request", 400)


async def realtime(request):
    if not authorized(request):
        return error("Authentication required", 401)
    try:
        upstream = await request.app["client"].ws_connect(
            ENGINE + "/v1/audio/transcriptions/realtime", heartbeat=30, timeout=10
        )
    except (ClientError, asyncio.TimeoutError):
        return error("ASR streaming engine unavailable", 502)
    downstream = web.WebSocketResponse(max_msg_size=4 * 1024 * 1024, heartbeat=30)
    await downstream.prepare(request)

    async def to_engine():
        async for msg in downstream:
            if msg.type == WSMsgType.TEXT:
                await upstream.send_str(msg.data)
            elif msg.type == WSMsgType.BINARY:
                await upstream.send_bytes(msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break

    async def to_client():
        async for msg in upstream:
            if msg.type == WSMsgType.TEXT:
                await downstream.send_str(msg.data)
            elif msg.type == WSMsgType.BINARY:
                await downstream.send_bytes(msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break

    tasks = [asyncio.create_task(to_engine()), asyncio.create_task(to_client())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await upstream.close()
        await downstream.close()
    return downstream


async def client_context(app):
    async with ClientSession() as session:
        app["client"] = session
        yield


def make_app():
    app = web.Application(client_max_size=MAX_INPUT)
    app.cleanup_ctx.append(client_context)
    app.router.add_get("/health", http_proxy)
    app.router.add_get("/ready", http_proxy)
    app.router.add_get("/v1/models", http_proxy)
    app.router.add_post("/v1/audio/transcriptions", transcribe)
    app.router.add_get("/v1/audio/transcriptions/realtime", realtime)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=8080, access_log=None)
