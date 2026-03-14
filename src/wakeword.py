"""
Wake word detection with Picovoice Porcupine. Uses custom "flowers" wake word.
After "flowers", listens for "play messages" and triggers playback via the local server.
"""
from dotenv import load_dotenv
import os
import time
import threading
import numpy as np
import pvporcupine
import sounddevice as sd
import speech_recognition as sr
import requests

load_dotenv()
access_key = os.environ.get("PICOVOICE_KEY")

# Custom "flowers" wake word: voice-models/flowers.ppn
_dir = os.path.dirname(os.path.abspath(__file__))
KEYWORD_PATH = os.path.join(_dir, "voice-models", "flowers.ppn")
if not os.path.isfile(KEYWORD_PATH):
    raise FileNotFoundError(
        f'Wake word model not found at {KEYWORD_PATH}. '
        "Add flowers.ppn to src/voice-models/ (create at https://console.picovoice.ai)."
    )

# Porcupine expects 16 kHz; try these device rates (ALSA often rejects 8 kHz)
CANDIDATE_RATES = [16000, 8000, 48000, 44100]
COMMAND_RECORD_SEC = 3.0
PLAY_MESSAGES_URL = os.environ.get("PLAY_MESSAGES_URL", "http://127.0.0.1:5000/play-latest")

porcupine = pvporcupine.create(
    access_key=access_key,
    keyword_paths=[KEYWORD_PATH],
)
PORCUPINE_RATE = porcupine.sample_rate
FRAME_LEN = porcupine.frame_length

# Command recording state (used from callback + worker thread)
_record_until = 0.0
_command_buffer = []
_lock = threading.Lock()


def pick_input_rate():
    for rate in CANDIDATE_RATES:
        try:
            sd.check_input_settings(device=None, channels=1, dtype="int16", samplerate=rate)
            return rate
        except sd.PortAudioError:
            continue
    raise RuntimeError(
        f"None of {CANDIDATE_RATES} Hz supported by input device. "
        "Check ALSA/PulseAudio and try a different mic."
    )


def resample_to_16k(pcm: np.ndarray, n_out: int) -> np.ndarray:
    n_in = len(pcm)
    if n_in == n_out:
        return pcm.astype(np.int16)
    x_old = np.arange(n_in, dtype=np.float64)
    x_new = np.linspace(0, n_in - 1, n_out, dtype=np.float64)
    return np.interp(x_new, x_old, pcm.astype(np.float64)).astype(np.int16)


def process_command_audio(audio_16k: np.ndarray):
    """Run STT and trigger play-latest if 'play messages' heard."""
    try:
        recognizer = sr.Recognizer()
        ad = sr.AudioData(audio_16k.tobytes(), 16000, 2)
        text = recognizer.recognize_google(ad, language="en-US")
    except sr.UnknownValueError:
        return
    except Exception:
        return
    text = (text or "").strip().lower()
    if "play messages" in text or "play message" in text:
        try:
            requests.post(PLAY_MESSAGES_URL, timeout=10)
        except requests.RequestException:
            pass


def make_callback(device_rate: int):
    def callback(indata, frames, time_info, status):
        global _record_until, _command_buffer
        pcm = np.squeeze(indata).astype(np.int16)
        pcm_16k = resample_to_16k(pcm, FRAME_LEN)
        if porcupine.process(pcm_16k.tolist()) >= 0:
            with _lock:
                _record_until = time.time() + COMMAND_RECORD_SEC

        with _lock:
            if _record_until > 0 and time.time() < _record_until:
                _command_buffer.append(pcm.copy())
                return
            if _record_until > 0 and time.time() >= _record_until and _command_buffer:
                chunks = _command_buffer.copy()
                _command_buffer = []
                _record_until = 0.0
            else:
                if _record_until > 0 and time.time() >= _record_until:
                    _record_until = 0.0
                return

        # Resample full command to 16 kHz and run STT in a thread
        raw = np.concatenate(chunks)
        n_out = int(len(raw) * 16000 / device_rate)
        audio_16k = resample_to_16k(raw, n_out)
        threading.Thread(target=process_command_audio, args=(audio_16k,), daemon=True).start()

    return callback


DEVICE_RATE = pick_input_rate()
blocksize = max(1, int(FRAME_LEN * DEVICE_RATE / PORCUPINE_RATE))

with sd.InputStream(
    samplerate=DEVICE_RATE,
    channels=1,
    dtype="int16",
    blocksize=blocksize,
    callback=make_callback(DEVICE_RATE),
):
    while True:
        time.sleep(0.1)
