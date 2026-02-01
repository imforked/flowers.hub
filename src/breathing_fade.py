# breathing_fade.py
import RPi.GPIO as GPIO
import time
import math

GPIO.setmode(GPIO.BCM)

PWM_PIN = 18
PWM_FREQUENCY = 1000

GPIO.setup(PWM_PIN, GPIO.OUT)
pwm = GPIO.PWM(PWM_PIN, PWM_FREQUENCY)
pwm.start(10)


def breathing_fade(
    min_duty=10,
    max_duty=100,
    period=4.0,
    steps=200,
):
    amplitude = (max_duty - min_duty) / 2
    offset = min_duty + amplitude

    try:
        while True:
            for i in range(steps):
                angle = 2 * math.pi * i / steps
                duty = offset + amplitude * math.sin(angle)
                pwm.ChangeDutyCycle(duty)
                time.sleep(period / steps)

    except Exception:
        pass
    finally:
        pwm.stop()
        GPIO.cleanup()
