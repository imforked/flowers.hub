"""
Breathing fade animation for RGB lights via PWM. Can be run until a stop condition (e.g. no unheard messages).
"""
import time
import math

try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False

PINS = [18, 23, 24]
FREQ = 2000
MIN_DUTY = 1
MAX_DUTY = 100
PERIOD = 4.0
STEPS = 400
GAMMA = 2.2
PHASES = [0, 2 * math.pi / 3, 4 * math.pi / 3]


def _build_wave():
    wave = []
    for step in range(STEPS):
        angle = 2 * math.pi * step / STEPS
        brightness = (math.sin(angle) + 1) / 2
        brightness = brightness ** GAMMA
        duty = MIN_DUTY + brightness * (MAX_DUTY - MIN_DUTY)
        wave.append(duty)
    return wave


_WAVE = _build_wave()
_PHASE_STEPS = [int(STEPS * phase / (2 * math.pi)) for phase in PHASES]

_pwms = None


def init_lights():
    """Initialize GPIO and PWM. Returns a controller (True if ready, False if GPIO not available)."""
    global _pwms
    if not _GPIO_AVAILABLE:
        return False
    if _pwms is not None:
        return True
    GPIO.setmode(GPIO.BCM)
    _pwms = []
    for pin in PINS:
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, FREQ)
        pwm.start(0)
        _pwms.append(pwm)
    return True


def lights_off():
    """Set all lights to off (duty cycle 0)."""
    if _pwms is None:
        return
    for pwm in _pwms:
        pwm.ChangeDutyCycle(0)


def cleanup_lights():
    """
    Turn off all lights, stop PWM, and release GPIO. Safe to call on process exit
    (e.g. from atexit). Idempotent; safe to call even if lights were never initialized.
    """
    global _pwms
    if not _GPIO_AVAILABLE:
        return
    if _pwms is not None:
        for pwm in _pwms:
            try:
                pwm.ChangeDutyCycle(0)
                pwm.stop()
            except Exception:
                pass
        _pwms = None
        try:
            GPIO.cleanup()
        except Exception:
            pass


def run_breathing_until(stop_check):
    """
    Run the breathing animation until stop_check() returns True.
    stop_check is called every step; when it returns True, animation stops and lights are turned off.
    """
    if _pwms is None:
        return
    while not stop_check():
        for step in range(STEPS):
            if stop_check():
                break
            for pwm, offset in zip(_pwms, _PHASE_STEPS):
                index = (step + offset) % STEPS
                pwm.ChangeDutyCycle(_WAVE[index])
            time.sleep(PERIOD / STEPS)
    lights_off()


def run_breathing_forever():
    """Run the breathing animation indefinitely (original script behavior)."""
    if _pwms is None:
        return
    try:
        while True:
            for step in range(STEPS):
                for pwm, offset in zip(_pwms, _PHASE_STEPS):
                    index = (step + offset) % STEPS
                    pwm.ChangeDutyCycle(_WAVE[index])
                time.sleep(PERIOD / STEPS)
    except KeyboardInterrupt:
        pass
    finally:
        lights_off()


if __name__ == "__main__":
    init_lights()
    try:
        run_breathing_forever()
    finally:
        if _pwms and _GPIO_AVAILABLE:
            for pwm in _pwms:
                pwm.stop()
            GPIO.cleanup()
