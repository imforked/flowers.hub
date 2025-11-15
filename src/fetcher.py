import requests
import base64
import os
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL")
UNHEARD_MESSAGES_ENDPOINT = f"{BACKEND_URL}/api/messages/unheard"


def fetch_unheard_messages() -> List[Dict[str, Any]]:
    """
    Fetches unheard messages from your server and returns a list of
    Python dicts containing:
    - id (str)
    - createdAt (str or ISO timestamp)
    - audio (bytes, decoded from base64)
    """

    try:
        response = requests.get(UNHEARD_MESSAGES_ENDPOINT, timeout=10)
        response.raise_for_status()
    except requests.RequestException as err:
        print(f"[fetcher] Error fetching messages: {err}")
        return []

    try:
        json_data = response.json()
    except ValueError as err:
        print(f"[fetcher] Could not parse JSON: {err}")
        return []

    messages = []

    for item in json_data:
        try:
            audio_bytes = base64.b64decode(item["audioData"])
            messages.append({
                "id": item["id"],
                "createdAt": item["createdAt"],
                "audio": audio_bytes,
            })
        except Exception as err:
            print(f"[fetcher] Error decoding message {item.get('id')}: {err}")

    return messages


# Tests `fetch_unheard_messages`
if __name__ == "__main__":
    msgs = fetch_unheard_messages()
    print(f"Fetched {len(msgs)} messages.")

    if msgs:
        first = msgs[0]
        print("Example message:")
        print(" ID:", first["id"])
        print(" createdAt:", first["createdAt"])
        print(" audio bytes:", len(first["audio"]))
