# Voice models

- **flowers.ppn** — Picovoice Porcupine wake word (“flowers”). Required.
- **vosk-model-small-en-us-0.15.zip** — Vosk model for on-device command recognition (“play messages”).

**On the Pi:** Unzip the Vosk model before first run:

```bash
cd src/voice-models
unzip vosk-model-small-en-us-0.15.zip
```

No further config needed; the app looks for `vosk-model-small-en-us-0.15/` in this directory by default.
