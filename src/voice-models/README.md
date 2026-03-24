# Voice models

## Wake word (“flowers”)

**PocketSphinx** keyword spotting (on-device, offline). Edit `wake-keyphrases.txt` to tune sensitivity; each line is `phrase /threshold/` (higher threshold = stricter, fewer false triggers). If the file is missing, the code falls back to the single keyphrase `flowers`.

Optional env: `WAKE_COOLDOWN_SEC` (default 1.5) to suppress duplicate wake fires.

## Command phrase (“play messages”)

**PocketSphinx** keyphrase mode. `command-keyphrases.txt` lists phrases (one per line). Install: `pip install PocketSphinx`.
