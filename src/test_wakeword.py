from dotenv import load_dotenv
import os
import pvporcupine
import sounddevice as sd
import numpy as np
import time

# Load environment variables from .env
load_dotenv()
access_key = os.environ.get("PICOVOICE_KEY")

# Porcupine requires 16 kHz; try these device rates (first supported wins)
CANDIDATE_RATES = [16000, 8000, 48000, 44100]

# Create Porcupine instance (expects 16 kHz)
porcupine = pvporcupine.create(
    access_key=access_key,
    keywords=["flowers"]
)

PORCUPINE_RATE = porcupine.sample_rate
FRAME_LEN = porcupine.frame_length


def pick_input_rate():
    """Use the first candidate rate the device supports (ALSA often rejects 8 kHz)."""
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


def resample_to_16k(pcm: np.ndarray, from_rate: int) -> np.ndarray:
    """Resample one frame from device rate to Porcupine's 16 kHz."""
    n_in = len(pcm)
    n_out = FRAME_LEN
    if n_in == n_out:
        return pcm.astype(np.int16)
    x_old = np.arange(n_in, dtype=np.float64)
    x_new = np.linspace(0, n_in - 1, n_out, dtype=np.float64)
    return np.interp(x_new, x_old, pcm.astype(np.float64)).astype(np.int16)


def make_callback(device_rate: int):
    def callback(indata, frames, time_info, status):
        pcm = np.squeeze(indata).astype(np.int16)
        pcm_16k = resample_to_16k(pcm, device_rate)
        if porcupine.process(pcm_16k.tolist()) >= 0:
            print("Wake word detected!")
    return callback


# Resolve device rate and block size
DEVICE_RATE = pick_input_rate()
# Samples per callback: one Porcupine frame worth of time at device rate
blocksize = max(1, int(FRAME_LEN * DEVICE_RATE / PORCUPINE_RATE))

if DEVICE_RATE != PORCUPINE_RATE:
    print(f"Listening at {DEVICE_RATE} Hz (resampled to {PORCUPINE_RATE} Hz for Porcupine)... say the wake word!")
else:
    print("Listening... say the wake word!")

with sd.InputStream(
    samplerate=DEVICE_RATE,
    channels=1,
    dtype="int16",
    blocksize=blocksize,
    callback=make_callback(DEVICE_RATE),
):
    while True:
        time.sleep(0.1)