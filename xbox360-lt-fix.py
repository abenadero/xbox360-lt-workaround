#!/usr/bin/python3

import time
from evdev import InputDevice, UInput, ecodes

DEVICE = "/dev/input/by-id/usb-©Microsoft_Corporation_Controller_1AB895F-event-joystick"

LT_MIN = 175
LT_MAX = 255


def fix_lt(value):
    if value <= LT_MIN:
        return 0

    value = (value - LT_MIN) * 255 // (LT_MAX - LT_MIN)

    return min(value, 255)


while True:
    try:
        dev = InputDevice(DEVICE)

        # Evita que las aplicaciones reciban también el mando físico.
        dev.grab()

        # Copia botones y ejes, pero no force-feedback.
        caps = dev.capabilities(absinfo=True)
        caps.pop(ecodes.EV_FF, None)
        caps.pop(ecodes.EV_SYN, None)

        ui = UInput(
            caps,
            name="Xbox 360 Controller (LT fixed)",
            bustype=dev.info.bustype,
            vendor=dev.info.vendor,
            product=dev.info.product,
            version=dev.info.version,
        )

        print(f"Using {DEVICE}")

        for event in dev.read_loop():
            if event.type == ecodes.EV_ABS and event.code == ecodes.ABS_Z:
                event.value = fix_lt(event.value)

            if event.type != ecodes.EV_SYN:
                ui.write_event(event)

            if event.type == ecodes.EV_SYN:
                ui.syn()

    except (FileNotFoundError, OSError):
        time.sleep(2)
