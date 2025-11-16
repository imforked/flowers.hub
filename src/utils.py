import os
import json

def ensure_dirs(storage_root: str):
    """
    Ensure the unheard/heard folders exist.
    """
    os.makedirs(os.path.join(storage_root, "unheard"), exist_ok=True)
    os.makedirs(os.path.join(storage_root, "heard"), exist_ok=True)


def save_unheard_message(storage_root: str, message_id: str, created_at: str, audio_bytes: bytes) -> str:
    """
    Saves audio_bytes to storage_root/unheard/<id>.wav
    and metadata to <id>.json.
    Returns the path to the WAV file.
    """
    ensure_dirs(storage_root)

    unheard_dir = os.path.join(storage_root, "unheard")
    wav_path = os.path.join(unheard_dir, f"{message_id}.wav")
    meta_path = os.path.join(unheard_dir, f"{message_id}.json")

    # Save audio file
    with open(wav_path, "wb") as f:
        f.write(audio_bytes)

    # Save metadata
    meta = {
        "id": message_id,
        "createdAt": created_at
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)

    return wav_path
