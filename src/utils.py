import os
import json
import subprocess

def ensure_dirs(storage_root: str):
    """
    Ensure the unheard/heard folders exist.
    """
    os.makedirs(os.path.join(storage_root, "unheard"), exist_ok=True)
    os.makedirs(os.path.join(storage_root, "heard"), exist_ok=True)


def _atomic_write(path: str, data, binary: bool = True) -> None:
    """
    Write data to path atomically and fsync to reduce SD card corruption risk
    on power loss (e.g. when USB mic causes brownout). Uses temp file + rename.
    """
    dirpath = os.path.dirname(path)
    fd, tmp_path = os.path.mkstemp(dir=dirpath, prefix=".tmp.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb" if binary else "w", encoding=None if binary else "utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_unheard_message(storage_root: str, message_id: str, created_at: str, audio_bytes: bytes) -> str:
    """
    Saves audio_bytes to storage_root/unheard/<id>.wav
    and metadata to <id>.json. Uses atomic write + fsync to reduce SD corruption
    risk on power brownouts (e.g. when plugging in USB microphone).
    Returns the path to the WAV file.
    """
    ensure_dirs(storage_root)

    unheard_dir = os.path.join(storage_root, "unheard")
    wav_path = os.path.join(unheard_dir, f"{message_id}.wav")
    meta_path = os.path.join(unheard_dir, f"{message_id}.json")

    _atomic_write(wav_path, audio_bytes, binary=True)

    meta = {
        "id": message_id,
        "createdAt": created_at
    }
    _atomic_write(meta_path, json.dumps(meta, indent=0), binary=False)

    return wav_path

def play_wav_file(file_path: str):
    # -nodisp hides video, -autoexit exits when done, -loglevel quiet silences FFmpeg messages
    subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", file_path])