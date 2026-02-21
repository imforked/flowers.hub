# breathing_fade_4ch.py
import RPi.GPIO as GPIO
import time

# GPIO pins connected to MOSFET board IN1–IN4
CHANNEL_PINS = [18, 23, 24, 25]  # Example GPIO pins; adjust as needed
PWM_FREQ = 500  # Hz, PWM frequency for LED fading
STEP_DELAY = 0.02  # seconds per duty cycle step

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Setup pins as output and create PWM objects
pwms = []
for pin in CHANNEL_PINS:
    GPIO.setup(pin, GPIO.OUT)
    pwm = GPIO.PWM(pin, PWM_FREQ)
    pwm.start(0)  # start with 0% duty cycle (off)
    pwms.append(pwm)

try:
    print("Starting breathing fade on all 4 channels. Press Ctrl+C to exit.")
    while True:
        # Fade in
        for duty in range(0, 101):
            for pwm in pwms:
                pwm.ChangeDutyCycle(duty)
            time.sleep(STEP_DELAY)
        # Fade out
        for duty in range(100, -1, -1):
            for pwm in pwms:
                pwm.ChangeDutyCycle(duty)
            time.sleep(STEP_DELAY)

except KeyboardInterrupt:
    print("\nExiting and cleaning up GPIO...")

finally:
    for pwm in pwms:
        pwm.stop()
    GPIO.cleanup()