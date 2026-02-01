import os
import base64
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from utils import save_unheard_message, ensure_dirs
import threading
from breathing_fade import breathing_fade

# Load environment variables
load_dotenv()

STORAGE_ROOT = os.getenv("STORAGE_DIR", "../messages")
PORT = int(os.getenv("PI_PORT", "5000"))

# Ensure folders exist
ensure_dirs(STORAGE_ROOT)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


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



def start_breathing():
    t = threading.Thread(
        target=breathing_fade,
        daemon=True,  # dies when Flask stops
    )
    t.start()


if __name__ == "__main__":
    start_breathing()
    app.run(host="0.0.0.0", port=PORT, debug=False)
