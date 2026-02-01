# breathing_fade.py
import RPi.GPIO as GPIO
import time

PWM_PIN = 18  # GPIO connected to MOSFET PWM1

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(PWM_PIN, GPIO.OUT)

def test_bulb():
    print("Testing MOSFET / bulb wiring...")

    # Try HIGH first
    print("Setting GPIO HIGH for 5 seconds (active HIGH test)")
    GPIO.output(PWM_PIN, GPIO.HIGH)
    time.sleep(5)
    GPIO.output(PWM_PIN, GPIO.LOW)
    time.sleep(1)

    # Try LOW in case module is active LOW
    print("Setting GPIO LOW for 5 seconds (active LOW test)")
    GPIO.output(PWM_PIN, GPIO.LOW)
    time.sleep(5)
    GPIO.output(PWM_PIN, GPIO.HIGH)
    time.sleep(1)

    print("Test finished. Cleaning up GPIO.")
    GPIO.cleanup()

if __name__ == "__main__":
    test_bulb()
