import RPi.GPIO as GPIO
import time
import math

# -----------------
# Config
# -----------------

PINS = [18, 23, 24]
FREQ = 2000

MIN_DUTY = 1
MAX_DUTY = 100

PERIOD = 4.0
STEPS = 400
GAMMA = 2.2

PHASES = [0, 2*math.pi/3, 4*math.pi/3]


# -----------------
# Build brightness table
# -----------------

def build_wave():
    wave = []

    for step in range(STEPS):

        angle = 2 * math.pi * step / STEPS

        brightness = (math.sin(angle) + 1) / 2
        brightness = brightness ** GAMMA

        duty = MIN_DUTY + brightness * (MAX_DUTY - MIN_DUTY)

        wave.append(duty)

    return wave


wave = build_wave()


# -----------------
# Setup GPIO
# -----------------

GPIO.setmode(GPIO.BCM)

pwms = []
for pin in PINS:
    GPIO.setup(pin, GPIO.OUT)
    pwm = GPIO.PWM(pin, FREQ)
    pwm.start(0)
    pwms.append(pwm)


# Convert phase offsets to step offsets
phase_steps = [
    int(STEPS * phase / (2 * math.pi))
    for phase in PHASES
]


# -----------------
# Animation loop
# -----------------

try:
    while True:

        for step in range(STEPS):

            for pwm, offset in zip(pwms, phase_steps):

                index = (step + offset) % STEPS
                pwm.ChangeDutyCycle(wave[index])

            time.sleep(PERIOD / STEPS)

except KeyboardInterrupt:
    pass

finally:
    for pwm in pwms:
        pwm.stop()

    GPIO.cleanup()