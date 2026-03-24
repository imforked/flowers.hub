"""
Wake word and command phrase detection with PocketSphinx (on-device, offline).

Flow: hear wake phrase "flowers", then within COMMAND_RECORD_SEC hear "play messages"
and invoke the callback. Uses ALSA on Linux (pyalsaaudio); PyAudio elsewhere.

SD-card safety: bounded command buffer, safe device open/close, and minimal
writes to avoid corruption on power brownouts when USB mics are connected.
"""
import os
import sys
import time
import threading
import array
import logging

try:
    from pocketsphinx import Decoder
except ImportError:
    Decoder = None

try:
    import alsaaudio
except ImportError:
    alsaaudio = None

logger = logging.getLogger(__name__)

CANDIDATE_RATES = [16000, 8000, 48000, 44100, 22050, 11025, 96000, 88200]
_COMMAND_RECORD_SEC_DEFAULT = 1.2
# ALSA / wake: fixed chunk size at 16 kHz (matches PocketSphinx expectation)
CHUNK_SAMPLES_16K = 1024

# Ignore duplicate wake fires within this window (seconds)
_WAKE_COOLDOWN_SEC_DEFAULT = 1.5


def _command_record_sec():
    try:
        v = os.environ.get("COMMAND_RECORD_SEC", "")
        return float(v) if v else _COMMAND_RECORD_SEC_DEFAULT
    except (TypeError, ValueError):
        return _COMMAND_RECORD_SEC_DEFAULT


def _wake_cooldown_sec():
    try:
        v = os.environ.get("WAKE_COOLDOWN_SEC", "")
        return float(v) if v else _WAKE_COOLDOWN_SEC_DEFAULT
    except (TypeError, ValueError):
        return _WAKE_COOLDOWN_SEC_DEFAULT


COMMAND_BUFFER_MAX_CHUNKS = 512
DEVICE_OPEN_RETRIES = 5
DEVICE_OPEN_RETRY_DELAY_SEC = 1.0

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WAKE_KEYPHRASES_FILE = os.path.join(_SCRIPT_DIR, "voice-models", "wake-keyphrases.txt")
COMMAND_KEYPHRASES_FILE = os.path.join(_SCRIPT_DIR, "voice-models", "command-keyphrases.txt")

_record_until = 0.0
_command_buffer = []
_lock = threading.Lock()

_command_decoder = None
_wake_decoder = None
_sphinx_lock = threading.Lock()
_last_wake_ts = 0.0


def _get_wake_decoder():
    """Keyword spotting for the wake phrase only (separate from command decoder)."""
    global _wake_decoder
    with _sphinx_lock:
        if _wake_decoder is not None:
            return _wake_decoder
        if Decoder is None:
            return None
        try:
            if os.path.isfile(WAKE_KEYPHRASES_FILE):
                _wake_decoder = Decoder(samprate=16000, kws=WAKE_KEYPHRASES_FILE, lm=None)
            else:
                _wake_decoder = Decoder(samprate=16000, keyphrase="flowers", lm=None)
            logger.info("PocketSphinx wake decoder loaded")
            return _wake_decoder
        except Exception as e:
            logger.warning("PocketSphinx wake decoder failed: %s", e)
            return None


def _get_command_decoder():
    """Keyphrase recognition for 'play messages' after wake."""
    global _command_decoder
    with _sphinx_lock:
        if _command_decoder is not None:
            return _command_decoder
        if Decoder is None:
            return None
        try:
            if os.path.isfile(COMMAND_KEYPHRASES_FILE):
                _command_decoder = Decoder(samprate=16000, kws=COMMAND_KEYPHRASES_FILE, lm=None)
            else:
                _command_decoder = Decoder(samprate=16000, keyphrase="play messages", lm=None)
            logger.info("PocketSphinx command decoder loaded")
            return _command_decoder
        except Exception as e:
            logger.warning("PocketSphinx command decoder failed: %s", e)
            return None


def _reset_wake_stream():
    """Clear wake decoder state after a command window or startup."""
    wd = _get_wake_decoder()
    if wd is None:
        return
    with _sphinx_lock:
        try:
            wd.end_utt()
        except Exception:
            pass
        try:
            wd.start_utt()
        except Exception:
            pass


def _feed_wake_and_detect(pcm_s16le_16k: bytes) -> bool:
    """
    Feed one chunk of 16 kHz mono s16le PCM. Return True if wake phrase detected.
    """
    global _last_wake_ts
    wd = _get_wake_decoder()
    if wd is None or not pcm_s16le_16k:
        return False
    with _sphinx_lock:
        wd.process_raw(pcm_s16le_16k, False, False)
        hyp = wd.hyp()
        if hyp is None:
            return False
        text = (hyp.hypstr or "").strip().lower()
        if "flowers" not in text:
            return False
        if time.time() - _last_wake_ts < _wake_cooldown_sec():
            try:
                wd.end_utt()
                wd.start_utt()
            except Exception:
                pass
            return False
        _last_wake_ts = time.time()
        try:
            wd.end_utt()
            wd.start_utt()
        except Exception:
            pass
        return True


def _recognize_command(audio_16k: array.array):
    decoder = _get_command_decoder()
    if decoder is None:
        return None
    with _sphinx_lock:
        try:
            decoder.start_utt()
            decoder.process_raw(audio_16k.tobytes(), full_utt=True)
            decoder.end_utt()
            hyp = decoder.hyp()
            text = (hyp.hypstr if hyp else "").strip().lower() or None
            return text
        except Exception as e:
            logger.debug("PocketSphinx recognition failed: %s", e)
            return None


def _process_command_audio(audio_16k: array.array, on_play_messages):
    text = _recognize_command(audio_16k)
    if text is None:
        logger.debug("Command phrase: no speech recognized")
        return
    logger.info("Heard after wake word: %r", text)
    if "play messages" in text or "play message" in text:
        on_play_messages()


def _pick_input_rate():
    import pyaudio as _pyaudio
    pa = _pyaudio.PyAudio()
    try:
        device_count = pa.get_device_count()

        forced = os.environ.get("AUDIO_INPUT_DEVICE", "").strip()
        try:
            forced_idx = int(forced) if forced else None
        except ValueError:
            forced_idx = None
        if forced_idx is not None and (forced_idx < 0 or forced_idx >= device_count):
            forced_idx = None

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

        if not input_indices and device_count > 0:
            for i in range(min(3, device_count)):
                if i not in input_indices:
                    input_indices.append(i)

        if not input_indices:
            raise RuntimeError(
                "No input devices found. Check ALSA/PulseAudio and microphone."
            )

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
    if n_in == 0:
        return array.array("h")
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


def _pcm_resample_to_16k(pcm: array.array, sample_rate: int) -> array.array:
    if sample_rate == 16000:
        return array.array("h", pcm)
    n_out = max(1, int(len(pcm) * 16000 / sample_rate))
    return _resample_to_16k(pcm, n_out)


def _pick_alsa_capture_card(periodsize: int):
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
        cards_to_try = ["1", "0"]
    for card in cards_to_try:
        try:
            pcm = alsaaudio.PCM(
                alsaaudio.PCM_CAPTURE,
                device=f"plughw:{card},0",
                rate=16000,
                channels=1,
                format=alsaaudio.PCM_FORMAT_S16_LE,
                periodsize=periodsize,
            )
            if hasattr(pcm, "close"):
                pcm.close()
            return card
        except Exception:
            continue
    return None


def _run_listener_alsa(on_play_messages, card: str):
    global _record_until, _command_buffer
    device = f"plughw:{card},0"
    pcm = alsaaudio.PCM(
        alsaaudio.PCM_CAPTURE,
        device=device,
        rate=16000,
        channels=1,
        format=alsaaudio.PCM_FORMAT_S16_LE,
        periodsize=CHUNK_SAMPLES_16K,
    )
    logger.info("Wake word listener using ALSA %s (16 kHz mono)", device)

    buf = array.array("h")
    _reset_wake_stream()
    try:
        while True:
            length, data = pcm.read()
            if length <= 0:
                continue
            pcm_chunk = array.array("h")
            pcm_chunk.frombytes(data)
            buf.extend(pcm_chunk)
            while len(buf) >= CHUNK_SAMPLES_16K:
                frame = array.array("h", buf[:CHUNK_SAMPLES_16K])
                del buf[:CHUNK_SAMPLES_16K]
                frame_bytes = frame.tobytes()

                now = time.time()
                recording_cmd = _record_until > 0 and now < _record_until
                if not recording_cmd and _feed_wake_and_detect(frame_bytes):
                    sec = _command_record_sec()
                    logger.info(
                        "Wake word 'flowers' detected — listening for command (%.1fs)",
                        sec,
                    )
                    with _lock:
                        _record_until = time.time() + sec

                with _lock:
                    now = time.time()
                    if _record_until > 0 and now < _record_until:
                        if len(_command_buffer) < COMMAND_BUFFER_MAX_CHUNKS:
                            _command_buffer.append(array.array("h", frame))
                        continue
                    if _record_until > 0 and now >= _record_until and _command_buffer:
                        chunks = list(_command_buffer)
                        _command_buffer.clear()
                        _record_until = 0.0
                    else:
                        if _record_until > 0 and now >= _record_until:
                            _record_until = 0.0
                            _reset_wake_stream()
                        continue

                raw_arr = array.array("h")
                for c in chunks:
                    raw_arr.extend(c)
                logger.debug(
                    "Sending %.1fs of audio for command recognition",
                    len(raw_arr) / 16000.0,
                )
                _reset_wake_stream()
                threading.Thread(
                    target=_process_command_audio,
                    args=(raw_arr, on_play_messages),
                    daemon=True,
                ).start()
    except KeyboardInterrupt:
        logger.info("Wake word listener interrupted")


def _open_stream_with_retry(pa, device_index, device_rate, chunk_size):
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
                    attempt + 1,
                    DEVICE_OPEN_RETRIES,
                    DEVICE_OPEN_RETRY_DELAY_SEC,
                    e,
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
    if Decoder is None:
        raise RuntimeError(
            "PocketSphinx is required for wake word. Install: pip install PocketSphinx"
        )
    if _get_wake_decoder() is None:
        raise RuntimeError(
            "PocketSphinx wake decoder could not be loaded. "
            f"Check {WAKE_KEYPHRASES_FILE} or install model files."
        )
    if _get_command_decoder() is None:
        raise RuntimeError(
            "PocketSphinx command decoder could not be loaded. "
            f"Check {COMMAND_KEYPHRASES_FILE}."
        )

    if sys.platform == "linux":
        if alsaaudio is None:
            raise RuntimeError(
                "On Linux, install pyalsaaudio for microphone support: pip install pyalsaaudio"
            )
        card = os.environ.get("AUDIO_INPUT_CARD", "").strip() or _pick_alsa_capture_card(
            CHUNK_SAMPLES_16K
        )
        if card is None:
            raise RuntimeError(
                "No ALSA capture device found. Run 'arecord -l' to see cards; "
                "if your USB mic is listed, ensure pyalsaaudio is installed and try again."
            )
        _run_listener_alsa(on_play_messages, card)
        return

    import pyaudio as _pyaudio
    device_index, device_rate = _pick_input_rate()
    chunk_size = 1024

    pa = _pyaudio.PyAudio()
    stream = None
    _reset_wake_stream()
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
            pcm_16k = _pcm_resample_to_16k(pcm, device_rate)

            now = time.time()
            recording_cmd = _record_until > 0 and now < _record_until
            if not recording_cmd and _feed_wake_and_detect(pcm_16k.tobytes()):
                sec = _command_record_sec()
                logger.info(
                    "Wake word 'flowers' detected — listening for command (%.1fs)",
                    sec,
                )
                with _lock:
                    _record_until = time.time() + sec

            with _lock:
                now = time.time()
                if _record_until > 0 and now < _record_until:
                    if len(_command_buffer) < COMMAND_BUFFER_MAX_CHUNKS:
                        _command_buffer.append(array.array("h", pcm))
                    continue
                if _record_until > 0 and now >= _record_until and _command_buffer:
                    chunks = list(_command_buffer)
                    _command_buffer.clear()
                    _record_until = 0.0
                else:
                    if _record_until > 0 and now >= _record_until:
                        _record_until = 0.0
                        _reset_wake_stream()
                    continue

            raw_arr = array.array("h")
            for c in chunks:
                raw_arr.extend(c)
            n_out = int(len(raw_arr) * 16000 / device_rate)
            audio_16k = _resample_to_16k(raw_arr, n_out)
            _reset_wake_stream()
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
