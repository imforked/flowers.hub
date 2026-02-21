import RPi.GPIO as GPIO
import time

PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.OUT)

# Turn MOSFET fully ON
GPIO.output(PIN, GPIO.LOW)  # try LOW first if active LOW
time.sleep(5)
GPIO.output(PIN, GPIO.HIGH)
time.sleep(2)
GPIO.cleanup()