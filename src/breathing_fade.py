import RPi.GPIO as GPIO
import time
import math

GPIO.cleanup()

PWM_PINS = [18, 23, 24]
PWM_FREQUENCY = 500

MIN_DUTY = 0
MAX_DUTY = 100
PERIOD = 4.0
STEPS = 200
GAMMA = 2.2   # human brightness perception correction

GPIO.setmode(GPIO.BCM)

pwms = []

for pin in PWM_PINS:
    GPIO.setup(pin, GPIO.OUT)
    pwm = GPIO.PWM(pin, PWM_FREQUENCY)
    pwm.start(0)
    pwms.append(pwm)


def apply_gamma(value):
    """
    value: 0.0 - 1.0 brightness
    returns gamma-corrected brightness
    """
    return pow(value, GAMMA)


def breathing_fade():

    phase_offsets = [
        0,
        2 * math.pi / 3,
        4 * math.pi / 3
    ]

    try:
        while True:
            for i in range(STEPS):

                base_angle = 2 * math.pi * i / STEPS

                for pwm, phase in zip(pwms, phase_offsets):

                    angle = base_angle + phase

                    # sine wave normalized to 0-1
                    brightness = (math.sin(angle) + 1) / 2

                    # apply gamma correction
                    brightness = apply_gamma(brightness)

                    duty = MIN_DUTY + brightness * (MAX_DUTY - MIN_DUTY)

                    pwm.ChangeDutyCycle(duty)

                time.sleep(PERIOD / STEPS)

    except KeyboardInterrupt:
        pass
    finally:
        for pwm in pwms:
            pwm.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    breathing_fade()