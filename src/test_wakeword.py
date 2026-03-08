from dotenv import load_dotenv
import os
import pvporcupine
import sounddevice as sd
import struct
import time

# Load environment variables from .env
load_dotenv()
access_key = os.environ.get("PICOVOICE_KEY")

# Create Porcupine instance
porcupine = pvporcupine.create(
    access_key=access_key,
    keywords=["picovoice"]
)

def callback(indata, frames, time_info, status):
    # Convert input to int16
    pcm = struct.unpack_from("h" * porcupine.frame_length, indata)
    if porcupine.process(pcm) >= 0:
        print("Wake word detected!")

print("Listening... say the wake word!")

# Open audio stream at Porcupine's required sample rate
with sd.InputStream(
    samplerate=porcupine.sample_rate,
    channels=1,
    dtype='int16',
    callback=callback
):
    while True:
        time.sleep(0.1)