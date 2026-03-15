"""
Wake word detection with Picovoice Porcupine. Uses custom "flowers" wake word.
After "flowers", listens for "play messages" and invokes the given callback.
Uses only stdlib + PyAudio (no numpy). Optional: pyalsaaudio for ALSA-direct capture.

SD-card safety: bounded command buffer, safe device open/close, and minimal
writes to avoid corruption on power brownouts when USB mics are connected.
"""
import os
import sys
import time
import threading
import array
import struct
import logging
import pvporcupine
import speech_recognition as sr

try:
    import alsaaudio
except ImportError:
    alsaaudio = None

logger = logging.getLogger(__name__)

CANDIDATE_RATES = [16000, 8000, 48000, 44100, 22050, 11025, 96000, 88200]
COMMAND_RECORD_SEC = 3.0
# Cap buffer to avoid unbounded memory growth (OOM/swap thrashing can corrupt SD)
COMMAND_BUFFER_MAX_CHUNKS = 512
# Retries when opening device (e.g. mic just plugged in / ALSA re-enumerating)
DEVICE_OPEN_RETRIES = 5
DEVICE_OPEN_RETRY_DELAY_SEC = 1.0

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KEYWORD_PATH = os.path.join(_SCRIPT_DIR, "voice-models", "flowers.ppn")

_record_until = 0.0
_command_buffer = []
_lock = threading.Lock()


def _pick_input_rate():
    """
    Find a working (device_index, sample_rate). Tries default input first,
    then all other input devices. Raises RuntimeError if no working input.
    """
    import pyaudio as _pyaudio
    pa = _pyaudio.PyAudio()
    try:
        device_count = pa.get_device_count()

        # Optional: force a device index (e.g. AUDIO_INPUT_DEVICE=1 for USB mic on card 1)
        forced = os.environ.get("AUDIO_INPUT_DEVICE", "").strip()
        try:
            forced_idx = int(forced) if forced else None
        except ValueError:
            forced_idx = None
        if forced_idx is not None and (forced_idx < 0 or forced_idx >= device_count):
            forced_idx = None

        # Build list of input device indices: forced first if set, then default, then rest
        input_indices = []
        if forced_idx is not None:
            input_indices.append(forced_idx)
        try:
            default_idx = pa.get_default_input_device_info().get("index")
            if default_idx is not None and int(default_idx) not in input_indices:
                input_indices.append(int(default_idx))
        except Exception:
            pass
        for i in range(device_count):
            try:
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0 and i not in input_indices:
                    input_indices.append(i)
            except Exception:
                continue

        # Some ALSA setups report 0 input channels for all devices; try first few indices anyway (e.g. USB mic on hub)
        if not input_indices and device_count > 0:
            for i in range(min(3, device_count)):
                if i not in input_indices:
                    input_indices.append(i)

        if not input_indices:
            raise RuntimeError(
                "No input devices found. Check ALSA/PulseAudio and microphone."
            )

        # For each device, prefer its default sample rate then candidate rates
        for device_index in input_indices:
            try:
                dev = pa.get_device_info_by_index(device_index)
                default_rate = int(dev.get("defaultSampleRate", 0))
                if default_rate > 0 and default_rate not in CANDIDATE_RATES:
                    rates_to_try = [default_rate] + CANDIDATE_RATES
                else:
                    rates_to_try = CANDIDATE_RATES
            except Exception:
                rates_to_try = CANDIDATE_RATES

            for rate in rates_to_try:
                try:
                    stream = pa.open(
                        format=_pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=1024,
                    )
                    stream.close()
                    return (device_index, rate)
                except Exception:
                    continue

        raise RuntimeError(
            "No supported input sample rate found on any device "
            f"(tried rates {CANDIDATE_RATES}). Check ALSA/PulseAudio and microphone."
        )
    finally:
        try:
            pa.terminate()
        except Exception:
            pass


def _resample_to_16k(pcm: array.array, n_out: int) -> array.array:
    """Linear interpolation resample to n_out int16 samples."""
    n_in = len(pcm)
    if n_in == n_out:
        return array.array("h", pcm)
    out = array.array("h")
    out_append = out.append
    for i in range(n_out):
        pos = (n_in - 1) * i / (n_out - 1) if n_out > 1 else 0
        j = int(pos)
        j = min(j, n_in - 2)
        frac = pos - j
        y0, y1 = pcm[j], pcm[j + 1]
        sample = int(y0 + (y1 - y0) * frac + 0.5)
        out_append(max(-32768, min(32767, sample)))
    return out


def _process_command_audio(audio_16k: array.array, on_play_messages):
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


def _pick_alsa_capture_card(frame_len: int):
    """
    Try opening ALSA plughw:N,0 for capture at 16 kHz. Return first card index that works, or None.
    Only tries cards 0 and 1 (Pi built-in + typical USB mic). Set AUDIO_INPUT_CARD for other cards.
    """
    if alsaaudio is None:
        return None
    forced = os.environ.get("AUDIO_INPUT_CARD", "").strip()
    try:
        forced_int = int(forced) if forced else None
    except ValueError:
        forced_int = None
    if forced_int is not None:
        cards_to_try = [str(forced_int), "1", "0"]
    else:
        cards_to_try = ["1", "0"]  # USB mic first, then built-in; avoid probing 2,3,4 (ALSA spam)
    for card in cards_to_try:
        try:
            pcm = alsaaudio.PCM(
                alsaaudio.PCM_CAPTURE,
                device=f"plughw:{card},0",
                rate=16000,
                channels=1,
                format=alsaaudio.PCM_FORMAT_S16_LE,
                periodsize=frame_len,
            )
            if hasattr(pcm, "close"):
                pcm.close()
            return card
        except Exception:
            continue
    return None


def _run_listener_alsa(porcupine, frame_len, on_play_messages, card: str):
    """
    Run the listener using ALSA directly (plughw:CARD,0). Bypasses PyAudio for reliable USB mic use.
    """
    global _record_until, _command_buffer
    device = f"plughw:{card},0"
    # 16 kHz mono so no resampling; plughw does rate conversion if the hardware rate differs
    pcm = alsaaudio.PCM(
        alsaaudio.PCM_CAPTURE,
        device=device,
        rate=16000,
        channels=1,
        format=alsaaudio.PCM_FORMAT_S16_LE,
        periodsize=frame_len,
    )
    logger.info("Wake word listener using ALSA %s (16 kHz mono)", device)

    buf = array.array("h")
    try:
        while True:
            length, data = pcm.read()
            if length <= 0:
                continue
            pcm_chunk = array.array("h")
            pcm_chunk.frombytes(data)
            buf.extend(pcm_chunk)
            while len(buf) >= frame_len:
                frame = array.array("h", buf[:frame_len])
                del buf[:frame_len]
                if porcupine.process(frame.tolist()) >= 0:
                    with _lock:
                        _record_until = time.time() + COMMAND_RECORD_SEC

                with _lock:
                    if _record_until > 0 and time.time() < _record_until:
                        if len(_command_buffer) < COMMAND_BUFFER_MAX_CHUNKS:
                            _command_buffer.append(array.array("h", frame))
                        continue
                    if _record_until > 0 and time.time() >= _record_until and _command_buffer:
                        chunks = list(_command_buffer)
                        _command_buffer.clear()
                        _record_until = 0.0
                    else:
                        if _record_until > 0 and time.time() >= _record_until:
                            _record_until = 0.0
                        continue

                raw_arr = array.array("h")
                for c in chunks:
                    raw_arr.extend(c)
                threading.Thread(
                    target=_process_command_audio,
                    args=(raw_arr, on_play_messages),
                    daemon=True,
                ).start()
    except KeyboardInterrupt:
        logger.info("Wake word listener interrupted")


def _open_stream_with_retry(pa, device_index, device_rate, chunk_size):
    """Open input stream with retries (handles mic hot-plug / ALSA re-enumeration)."""
    import pyaudio as _pyaudio
    last_err = None
    for attempt in range(DEVICE_OPEN_RETRIES):
        try:
            stream = pa.open(
                format=_pyaudio.paInt16,
                channels=1,
                rate=device_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size,
            )
            return stream
        except Exception as e:
            last_err = e
            if attempt < DEVICE_OPEN_RETRIES - 1:
                logger.warning(
                    "Audio device open failed (attempt %s/%s), retrying in %.1fs: %s",
                    attempt + 1, DEVICE_OPEN_RETRIES, DEVICE_OPEN_RETRY_DELAY_SEC, e,
                )
                time.sleep(DEVICE_OPEN_RETRY_DELAY_SEC)
    raise RuntimeError(
        f"Could not open microphone after {DEVICE_OPEN_RETRIES} attempts. "
        "If you just plugged in the mic, wait a few seconds and try again."
    ) from last_err


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

    # On Linux use ALSA (pyalsaaudio) only—PyAudio/PortAudio is unreliable with USB mics there
    if sys.platform == "linux":
        if alsaaudio is None:
            raise RuntimeError(
                "On Linux, install pyalsaaudio for microphone support: pip install pyalsaaudio"
            )
        card = os.environ.get("AUDIO_INPUT_CARD", "").strip() or _pick_alsa_capture_card(frame_len)
        if card is None:
            raise RuntimeError(
                "No ALSA capture device found. Run 'arecord -l' to see cards; "
                "if your USB mic is listed, ensure pyalsaaudio is installed and try again."
            )
        try:
            _run_listener_alsa(porcupine, frame_len, on_play_messages, card)
        finally:
            porcupine.delete()
        return

    import pyaudio as _pyaudio
    device_index, device_rate = _pick_input_rate()
    chunk_size = max(1, int(frame_len * device_rate / porcupine_rate))

    pa = _pyaudio.PyAudio()
    stream = None
    try:
        stream = _open_stream_with_retry(pa, device_index, device_rate, chunk_size)
        while True:
            try:
                raw = stream.read(chunk_size, exception_on_overflow=False)
            except Exception as e:
                logger.warning("Stream read error (device may have been unplugged): %s", e)
                break
            pcm = array.array("h")
            pcm.frombytes(raw)
            pcm_16k = _resample_to_16k(pcm, frame_len)
            if porcupine.process(pcm_16k.tolist()) >= 0:
                with _lock:
                    _record_until = time.time() + COMMAND_RECORD_SEC

            with _lock:
                if _record_until > 0 and time.time() < _record_until:
                    if len(_command_buffer) < COMMAND_BUFFER_MAX_CHUNKS:
                        _command_buffer.append(array.array("h", pcm))
                    continue
                if _record_until > 0 and time.time() >= _record_until and _command_buffer:
                    chunks = list(_command_buffer)
                    _command_buffer.clear()
                    _record_until = 0.0
                else:
                    if _record_until > 0 and time.time() >= _record_until:
                        _record_until = 0.0
                    continue

            raw_arr = array.array("h")
            for c in chunks:
                raw_arr.extend(c)
            n_out = int(len(raw_arr) * 16000 / device_rate)
            audio_16k = _resample_to_16k(raw_arr, n_out)
            threading.Thread(
                target=_process_command_audio,
                args=(audio_16k, on_play_messages),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        logger.info("Wake word listener interrupted")
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        try:
            pa.terminate()
        except Exception:
            pass
        porcupine.delete()

