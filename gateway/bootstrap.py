"""Initialize persistent GGUF and per-install bearer key for the Portainer stack."""
import hashlib
import os
from pathlib import Path
import secrets
import tempfile
from urllib.request import urlopen

MODEL_NAME = "nemotron-3.5-asr-streaming-0.6b.q8_0.gguf"
MODEL_REVISION = "ea30d66debe3740a08b573244286791d423d6b3e"
MODEL_URL = (
    "https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b/resolve/"
    f"{MODEL_REVISION}/{MODEL_NAME}"
)
MODEL_SHA256 = "3fc991d3badad7277c11030a7519832cddaf2057aafed6d4b25147e953a070b1"


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def prepare_model(destination, url, expected):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or digest(destination) != expected:
            raise RuntimeError("Existing model checksum mismatch; refusing to overwrite")
        print("Model verified (cached)", flush=True)
        return

    # The partial download is private to this process and never mounted as the live model.
    fd, temporary = tempfile.mkstemp(prefix=".model-download-", dir=destination.parent)
    temporary = Path(temporary)
    try:
        checksum = hashlib.sha256()
        with os.fdopen(fd, "wb") as output, urlopen(url, timeout=90) as response:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                output.write(chunk)
                checksum.update(chunk)
        if checksum.hexdigest() != expected:
            raise RuntimeError("Downloaded model checksum mismatch; refusing to mount")
        temporary.chmod(0o644)
        os.replace(temporary, destination)
        print("Model downloaded and verified", flush=True)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_key(path, uid, gid):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # O_EXCL prevents replacing an existing key on a second bootstrap.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(secrets.token_urlsafe(32) + "\n")
    if not path.is_file() or not path.read_text().strip():
        raise RuntimeError("Stored API key is invalid")
    stat = path.stat()
    if stat.st_uid != uid or stat.st_gid != gid:
        os.chown(path, uid, gid)
    # The unprivileged gateway can read via its group but cannot rewrite the key.
    path.chmod(0o640)
    print("Bearer key ready (not printed)", flush=True)


def main():
    destination = Path(os.getenv("ASR_BOOTSTRAP_MODEL_PATH", "/models/" + MODEL_NAME))
    key_path = Path(os.getenv("ASR_BOOTSTRAP_KEY_PATH", "/run/asr-auth/api_key"))
    url = os.getenv("ASR_BOOTSTRAP_MODEL_URL", MODEL_URL)
    expected = os.getenv("ASR_BOOTSTRAP_SHA256", MODEL_SHA256)
    uid = int(os.getenv("ASR_BOOTSTRAP_UID", "0"))
    gid = int(os.getenv("ASR_BOOTSTRAP_GID", "65532"))
    prepare_model(destination, url, expected)
    prepare_key(key_path, uid, gid)


if __name__ == "__main__":
    main()
