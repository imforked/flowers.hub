import RPi.GPIO as GPIO
import time
import math

PWM_PIN = 18
PWM_FREQUENCY = 500
MIN_DUTY = 50
MAX_DUTY = 100
PERIOD = 4.0
STEPS = 200

GPIO.setmode(GPIO.BCM)
GPIO.setup(PWM_PIN, GPIO.OUT)
GPIO.cleanup()

pwm = GPIO.PWM(PWM_PIN, PWM_FREQUENCY)
pwm.start(MIN_DUTY)

def breathing_fade(min_duty=MIN_DUTY, max_duty=MAX_DUTY, period=PERIOD, steps=STEPS):
    amplitude = (max_duty - min_duty) / 2
    offset = min_duty + amplitude

    try:
        while True:
            for i in range(steps):
                angle = 2 * math.pi * i / steps
                duty = offset + amplitude * math.sin(angle)
                pwm.ChangeDutyCycle(duty)
                time.sleep(period / steps)
    except KeyboardInterrupt:
        pass
    finally:
        pwm.stop()
        GPIO.cleanup()

def static_test(seconds=5):
    GPIO.output(PWM_PIN, GPIO.HIGH)
    time.sleep(seconds)
    GPIO.output(PWM_PIN, GPIO.LOW)

if __name__ == "__main__":
    static_test(5)
    breathing_fade()
