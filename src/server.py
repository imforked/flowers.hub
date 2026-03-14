import os
import base64
import logging
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import shutil
from utils import save_unheard_message, ensure_dirs, play_wav_file

# Load environment variables
load_dotenv()

STORAGE_ROOT = os.getenv("STORAGE_DIR", os.path.expanduser("~/messages"))
PORT = int(os.path.getenv("PI_PORT", "5000"))

# Ensure folders exist
ensure_dirs(STORAGE_ROOT)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


def play_latest_message():
    """
    Play the latest unheard message and move it to heard. In-process only; no HTTP.
    Returns (success: bool, file_name_or_error: str | None).
    """
    unheard_dir = os.path.join(STORAGE_ROOT, "unheard")
    heard_dir = os.path.join(STORAGE_ROOT, "heard")
    os.makedirs(heard_dir, exist_ok=True)
    wav_files = [
        os.path.join(unheard_dir, f)
        for f in os.listdir(unheard_dir)
        if f.endswith(".wav")
    ]
    if not wav_files:
        return False, None
    wav_files.sort(key=os.path.getmtime, reverse=True)
    latest_wav_path = wav_files[0]
    latest_wav_name = os.path.basename(latest_wav_path)
    latest_json_path = os.path.join(unheard_dir, latest_wav_name.replace(".wav", ".json"))
    play_wav_file(latest_wav_path)
    shutil.move(latest_wav_path, os.path.join(heard_dir, latest_wav_name))
    if os.path.exists(latest_json_path):
        shutil.move(latest_json_path, os.path.join(heard_dir, os.path.basename(latest_json_path)))
    return True, latest_wav_name


@app.route("/test", methods=["GET"])
def test_route():
    app.logger.info('"/test" was hit')
    return jsonify({"message": '"/test" was hit'}), 200


@app.route("/new-message", methods=["POST"])
def new_message():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "no json body"}), 400

    if not all(k in data for k in ["id", "createdAt", "audioData"]):
        return jsonify({"error": "missing fields"}), 400

    message_id = str(data["id"])
    created_at = data["createdAt"]
    audio_b64 = data["audioData"]

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as exc:
        return jsonify({"error": f"invalid base64: {exc}"}), 400

    try:
        wav_path = save_unheard_message(STORAGE_ROOT, message_id, created_at, audio_bytes)
    except Exception as exc:
        app.logger.error("Failed to save message: %s", exc)
        return jsonify({"error": "save failed"}), 500

    app.logger.info("Saved message %s -> %s", message_id, wav_path)
    return jsonify({"status": "saved", "id": message_id}), 201


@app.route("/play-latest", methods=["POST"])
def play_latest():
    app.logger.info("Looking for WAVs in: %s", os.path.join(STORAGE_ROOT, "unheard"))
    success, result = play_latest_message()
    if not success:
        return jsonify({"error": "no unheard messages"}), 404
    app.logger.info("Playing %s", result)
    return jsonify({"status": "played", "file": result}), 200


def _start_wake_word_listener():
    try:
        from wakeword import run_listener
        run_listener(on_play_messages=play_latest_message)
    except FileNotFoundError as e:
        app.logger.warning("Wake word not started: %s", e)
    except ValueError as e:
        app.logger.warning("Wake word not started: %s", e)
    except Exception as e:
        app.logger.exception("Wake word listener error: %s", e)


if __name__ == "__main__":
    thread = threading.Thread(target=_start_wake_word_listener, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=PORT, debug=True)
