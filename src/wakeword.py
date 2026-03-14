"""
Wake word detection with Picovoice Porcupine. Uses custom "flowers" wake word.
After "flowers", listens for "play messages" and invokes the given callback.
"""
import os
import time
import threading
import numpy as np
import pvporcupine
import sounddevice as sd
import speech_recognition as sr

CANDIDATE_RATES = [16000, 8000, 48000, 44100]
COMMAND_RECORD_SEC = 3.0

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KEYWORD_PATH = os.path.join(_SCRIPT_DIR, "voice-models", "flowers.ppn")

_record_until = 0.0
_command_buffer = []
_lock = threading.Lock()


def _pick_input_rate():
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


def _resample_to_16k(pcm: np.ndarray, n_out: int) -> np.ndarray:
    n_in = len(pcm)
    if n_in == n_out:
        return pcm.astype(np.int16)
    x_old = np.arange(n_in, dtype=np.float64)
    x_new = np.linspace(0, n_in - 1, n_out, dtype=np.float64)
    return np.interp(x_new, x_old, pcm.astype(np.float64)).astype(np.int16)


def _process_command_audio(audio_16k: np.ndarray, on_play_messages):
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
        on_play_messages()


def run_listener(on_play_messages):
    """
    Run the wake word listener in the current thread. Blocks until the process exits.
    When "play messages" is heard after "flowers", calls on_play_messages() (no arguments).
    """
    global _record_until, _command_buffer
    if not os.path.isfile(KEYWORD_PATH):
        raise FileNotFoundError(
            f"Wake word model not found at {KEYWORD_PATH}. "
            "Add flowers.ppn to src/voice-models/ (create at https://console.picovoice.ai)."
        )
    access_key = os.environ.get("PICOVOICE_KEY")
    if not access_key:
        raise ValueError("PICOVOICE_KEY environment variable is required for wake word.")

    porcupine = pvporcupine.create(
        access_key=access_key,
        keyword_paths=[KEYWORD_PATH],
    )
    porcupine_rate = porcupine.sample_rate
    frame_len = porcupine.frame_length

    device_rate = _pick_input_rate()
    blocksize = max(1, int(frame_len * device_rate / porcupine_rate))

    def callback(indata, frames, time_info, status):
        global _record_until, _command_buffer
        pcm = np.squeeze(indata).astype(np.int16)
        pcm_16k = _resample_to_16k(pcm, frame_len)
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

        raw = np.concatenate(chunks)
        n_out = int(len(raw) * 16000 / device_rate)
        audio_16k = _resample_to_16k(raw, n_out)
        threading.Thread(
            target=_process_command_audio,
            args=(audio_16k, on_play_messages),
            daemon=True,
        ).start()

    with sd.InputStream(
        samplerate=device_rate,
        channels=1,
        dtype="int16",
        blocksize=blocksize,
        callback=callback,
    ):
        while True:
            time.sleep(0.1)
