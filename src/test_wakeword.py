from dotenv import load_dotenv
import os
import pvporcupine
import sounddevice as sd
import numpy as np
import time

# Load environment variables from .env
load_dotenv()
access_key = os.environ.get("PICOVOICE_KEY")

# Mic sample rate (e.g. 8 kHz); Porcupine requires 16 kHz
MIC_SAMPLE_RATE = 8000

# Create Porcupine instance (expects 16 kHz)
porcupine = pvporcupine.create(
    access_key=access_key,
    keywords=["picovoice"]
)

def resample_8k_to_16k(pcm_8k: np.ndarray) -> np.ndarray:
    """Resample one frame from 8 kHz to 16 kHz (2x upsample) for Porcupine."""
    n_in = len(pcm_8k)
    n_out = porcupine.frame_length
    # Linear interpolation: map n_in samples -> n_out samples
    x_old = np.arange(n_in, dtype=np.float64)
    x_new = np.linspace(0, n_in - 1, n_out, dtype=np.float64)
    return np.interp(x_new, x_old, pcm_8k.astype(np.float64)).astype(np.int16)


def callback(indata, frames, time_info, status):
    # indata is (frames,) or (frames, 1) at 8 kHz; we need frame_length/2 samples
    pcm_8k = np.squeeze(indata).astype(np.int16)
    pcm_16k = resample_8k_to_16k(pcm_8k)
    if porcupine.process(pcm_16k.tolist()) >= 0:
        print("Wake word detected!")


print("Listening at 8 kHz (resampled to 16 kHz for Porcupine)... say the wake word!")

# One Porcupine frame at 16 kHz = half as many samples at 8 kHz
frame_length_8k = porcupine.frame_length // 2

with sd.InputStream(
    samplerate=MIC_SAMPLE_RATE,
    channels=1,
    dtype="int16",
    blocksize=frame_length_8k,
    callback=callback,
):
    while True:
        time.sleep(0.1)