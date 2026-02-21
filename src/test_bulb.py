import RPi.GPIO as GPIO
import time

PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.OUT)

# Turn on the MOSFET manually
GPIO.output(PIN, GPIO.LOW)  # Active LOW test
time.sleep(5)
GPIO.output(PIN, GPIO.HIGH)
time.sleep(2)

GPIO.cleanup()