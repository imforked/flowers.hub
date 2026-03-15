# Voice models

- **flowers.ppn** — Picovoice Porcupine wake word (“flowers”). Required.
- **Vosk model** — For on-device “play messages” recognition. Not in repo (too large to push).

**On the Pi:** Download and unzip the small English model before first run:

```bash
cd src/voice-models
curl -L -o vosk-model-small-en-us-0.15.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

No further config needed; the app looks for `vosk-model-small-en-us-0.15/` in this directory by default.
