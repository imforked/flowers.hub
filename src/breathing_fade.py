import RPi.GPIO as GPIO
import time
import math

GPIO.cleanup()

PWM_PINS = [18, 23, 24]
PWM_FREQUENCY = 500

MIN_DUTY = 50
MAX_DUTY = 100
PERIOD = 4.0
STEPS = 200

GPIO.setmode(GPIO.BCM)

pwms = []

# Setup each PWM channel
for pin in PWM_PINS:
    GPIO.setup(pin, GPIO.OUT)
    pwm = GPIO.PWM(pin, PWM_FREQUENCY)
    pwm.start(MIN_DUTY)
    pwms.append(pwm)


def breathing_fade(min_duty=MIN_DUTY, max_duty=MAX_DUTY, period=PERIOD, steps=STEPS):
    amplitude = (max_duty - min_duty) / 2
    offset = min_duty + amplitude

    # Each bulb gets a phase shift
    phase_offsets = [
        0,
        2 * math.pi / 3,
        4 * math.pi / 3
    ]

    try:
        while True:
            for i in range(steps):

                base_angle = 2 * math.pi * i / steps

                for pwm, phase in zip(pwms, phase_offsets):
                    angle = base_angle + phase
                    duty = offset + amplitude * math.sin(angle)
                    pwm.ChangeDutyCycle(duty)

                time.sleep(period / steps)

    except KeyboardInterrupt:
        pass
    finally:
        for pwm in pwms:
            pwm.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    breathing_fade()