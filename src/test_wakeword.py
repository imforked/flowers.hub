#!/usr/bin/env python3
"""
Test the wake word listener in isolation (no Flask server).
Run from project root:  python src/test_wakeword.py
Or from src/:             python test_wakeword.py

Requires: .env with PICOVOICE_KEY, src/voice-models/flowers.ppn, and Vosk model at src/voice-models/vosk-model-small-en-us-0.15/

Then say "flowers" and within a few seconds "play messages" (or "play message").
You should see "*** PLAY MESSAGES TRIGGERED ***" when it works.
Press Ctrl+C to stop.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(_root / ".env")

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# Add src to path for imports when run from root
_src = Path(__file__).resolve().parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from wakeword import run_listener


def on_play_messages():
    print("\n*** PLAY MESSAGES TRIGGERED ***\n")


if __name__ == "__main__":
    print("Listening for 'flowers' then 'play messages'... (Ctrl+C to stop)")
    run_listener(on_play_messages=on_play_messages)
