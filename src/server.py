from flask import Flask, request, jsonify
import threading
from breathing_fade import breathing_fade

app = Flask(__name__)

@app.route("/test", methods=["GET"])
def test_route():
    return {"message": "Server is running!"}

@app.route("/new-message", methods=["POST"])
def new_message():
    data = request.get_json(force=True)
    if not data or not all(k in data for k in ["id", "createdAt", "audioData"]):
        return jsonify({"error": "missing fields"}), 400
    # Handle saving message here if needed
    return jsonify({"status": "saved", "id": str(data["id"])}), 201

if __name__ == "__main__":
    t = threading.Thread(target=breathing_fade, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
