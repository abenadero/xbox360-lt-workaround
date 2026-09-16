# Xbox 360 LT Trigger Calibration Workaround on Linux

## Overview

This workaround is for an Xbox 360 controller (but theory can be applied to other controllers) whose **LT trigger is electrically functional but reports the wrong analog range**.

It would be better, if you can and it would solve the issue, to buy a replacement. But if, for whatever reason, you want a software workaround,
this is a good place to start.

In the affected controller used for this workaround:

- Linux exposes LT as `ABS_Z`.
- LT does not rest at `0`; instead it rests around `165-170`.
- LT reaches `255` too early, roughly around the middle of the physical trigger travel.
- RT behaves normally.
- The hardware fault is specific to LT, but the remaining LT signal is still stable enough to be remapped in software.

The workaround:

1. Opens only the affected physical controller.
2. Grabs it exclusively so applications do not also receive the broken raw input.
3. Creates a virtual controller through `uinput`.
4. Copies all buttons and axes unchanged.
5. Remaps only `ABS_Z` (LT).
6. Runs automatically through a systemd service.

This is intentionally specific to one physical controller so that other controllers can remain connected without being modified.

---

## Requirements

Fedora package (you can search for the package on other package managers):

```bash
sudo dnf install python3-evdev
```

You will also need `evtest` for calibration and verification:

```bash
sudo dnf install evtest
```

---

## 1. Identify the affected controller

Connect the controller and inspect persistent input-device names:

```bash
ls -l /dev/input/by-id/
```

For the controller used when this workaround was created, the persistent device path was:

```text
/dev/input/by-id/usb-©Microsoft_Corporation_Controller_1AB895F-event-joystick
```

The important part is that this path identifies the **specific physical controller**, rather than using a temporary path such as:

```text
/dev/input/event22
```

`event22` can change after rebooting or after connecting other input devices.

### What to change on another computer or for another controller

Find the corresponding `*-event-joystick` entry under:

```bash
/dev/input/by-id/
```

Then copy its full path into the `DEVICE` variable in the script below.

For example:

```python
DEVICE = "/dev/input/by-id/usb-©Microsoft_Corporation_Controller_1AB895F-event-joystick"
```

Do not identify the controller only by Xbox vendor/product IDs if you own several identical Xbox 360 controllers, because different physical controllers may expose the same USB vendor/product IDs.

---

## 2. Measure the broken LT range

The Xbox 360 LT trigger is exposed by Linux as:

```text
ABS_Z
```

Use:

```bash
sudo evtest /dev/input/eventXX
```

or, once the correct event device is known:

```bash
sudo evtest /dev/input/event22 | grep --line-buffered 'ABS_Z)'
```

Replace `event22` with the actual event device used by the controller.

For the affected controller used here, the raw LT values were approximately:

```text
LT released:      165-170
LT fully pressed: 255
```

The value also drifted slightly after use, sometimes reaching approximately `170-172` while released.

This is why the software workaround needs a configurable minimum threshold.

---

## 3. Choose `LT_MIN`

The script treats every raw LT value at or below `LT_MIN` as fully released.

Example:

```python
LT_MIN = 175
```

With this value:

```text
raw 0..175   -> virtual 0
raw 176..255 -> virtual 0..255, rescaled
```

### How to choose the correct value

Observe LT while the trigger is fully released:

```bash
sudo evtest /dev/input/eventXX | grep --line-buffered 'ABS_Z)'
```

Do not touch LT for a few seconds and note the highest value seen.

If the released trigger fluctuates around:

```text
165-170
```

a sensible starting value is:

```python
LT_MIN = 175
```

The value should be slightly above the highest idle value to provide a small dead zone.

Examples:

```text
Idle around 150-154 -> LT_MIN = 158
Idle around 165-170 -> LT_MIN = 175
Idle around 170-174 -> LT_MIN = 178
```

Do not make `LT_MIN` unnecessarily high. The physical controller already has reduced usable trigger travel, so every extra point removed from the low end further reduces analog resolution.

`LT_MAX` normally remains:

```python
LT_MAX = 255
```

---

## 4. Install the workaround script

Create:

```bash
sudo nano /usr/local/bin/xbox360-lt-fix.py
```

Use the following script (change DEVICE to your device):

```python
#!/usr/bin/python3

import time
from evdev import InputDevice, UInput, ecodes

# Persistent path of the specific broken controller.
DEVICE = "/dev/input/by-id/usb-©Microsoft_Corporation_Controller_1AB895F-event-joystick"

# Raw LT calibration values.
#
# All LT values <= LT_MIN become 0.
# Values from LT_MIN..LT_MAX are rescaled to 0..255.
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

        # Prevent applications from receiving the uncorrected physical
        # controller at the same time as the virtual corrected controller.
        dev.grab()

        # Clone the controller capabilities, excluding force feedback.
        # This workaround intentionally does not preserve rumble.
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
            # Xbox 360 LT is ABS_Z.
            if event.type == ecodes.EV_ABS and event.code == ecodes.ABS_Z:
                event.value = fix_lt(event.value)

            if event.type != ecodes.EV_SYN:
                ui.write_event(event)

            if event.type == ecodes.EV_SYN:
                ui.syn()

    except (FileNotFoundError, OSError):
        # Controller disconnected or not yet present.
        # Retry periodically so the service can remain running.
        time.sleep(2)
```

Make it executable:

```bash
sudo chmod +x /usr/local/bin/xbox360-lt-fix.py
```

---

## 5. Create the systemd service

Create:

```bash
sudo nano /etc/systemd/system/xbox360-lt-fix.service
```

Contents:

```ini
[Unit]
Description=Xbox 360 LT calibration workaround

[Service]
Type=simple
ExecStart=/usr/local/bin/xbox360-lt-fix.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Reload systemd and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xbox360-lt-fix.service
```

Check its status:

```bash
systemctl status xbox360-lt-fix.service
```

Follow its logs:

```bash
journalctl -u xbox360-lt-fix.service -f
```

---

## 6. Verify the virtual controller

Run:

```bash
sudo evtest
```

A new controller should appear with a name similar to:

```text
Xbox 360 Controller (LT fixed)
```

Select that virtual controller.

The corrected LT axis should be:

```text
ABS_Z
```

Expected behavior:

```text
LT released      -> 0
LT pressed       -> increases progressively
LT fully pressed -> 255
```

If LT still shows a small value while released, increase:

```python
LT_MIN = 175
```

slightly, for example:

```python
LT_MIN = 178
```

Then restart the service:

```bash
sudo systemctl restart xbox360-lt-fix.service
```

If LT begins responding too late, reduce `LT_MIN`.

---

## How the remapping works

The broken controller provides only part of the expected raw range.

Example:

```text
Physical LT raw range:

released                         pressed
   170 ----------------------------- 255
```

The workaround transforms that into:

```text
Virtual LT range:

released                         pressed
    0 ------------------------------ 255
```

The effective transformation is:

```text
if raw <= LT_MIN:
    output = 0
else:
    output = (raw - LT_MIN) * 255 / (LT_MAX - LT_MIN)
```

For:

```text
LT_MIN = 175
LT_MAX = 255
```

approximately:

```text
Raw input    Virtual output
---------    --------------
175          0
180          15
190          47
200          79
210          111
220          143
230          175
240          207
250          239
255          255
```

The exact integer values depend on integer rounding.

---

## Important limitation

This workaround can correct the reported software range, but it **cannot restore physical analog resolution that the controller no longer produces**.

If the physical controller reaches raw `255` halfway through the trigger travel, Linux cannot distinguish:

```text
50% physical travel
```

from:

```text
100% physical travel
```

once both positions already produce:

```text
255
```

The script therefore makes the remaining usable range convenient and correctly centered, but it cannot recreate missing hardware information.

For games where LT behaves mainly like a button, this is usually acceptable.

For games that depend heavily on precise analog trigger position, the reduced physical resolution remains a limitation.

---

## Why use a virtual controller?

The original controller continues to report the faulty LT values.

If the script simply created a corrected virtual controller without blocking the original device, games could detect both:

```text
Physical Xbox 360 controller
Virtual Xbox 360 Controller (LT fixed)
```

That could cause duplicate inputs.

The call:

```python
dev.grab()
```

requests exclusive access to the physical event device.

Applications then receive the corrected virtual controller instead of simultaneously receiving both versions.

This affects only the device opened through the configured `DEVICE` path.

Other controllers remain untouched.

---

## Multiple controllers

This workaround is intentionally configured using:

```text
/dev/input/by-id/
```

instead of generic Xbox USB IDs.

For example:

```python
DEVICE = "/dev/input/by-id/usb-©Microsoft_Corporation_Controller_1AB895F-event-joystick"
```

This means other controllers can remain connected normally.

If moving the workaround to another Linux machine, check:

```bash
ls -l /dev/input/by-id/
```

and verify that the persistent name for this controller is the same.

If it differs, update `DEVICE`.

---

## Changing calibration later

Edit:

```bash
sudo nano /usr/local/bin/xbox360-lt-fix.py
```

The two values that normally matter are:

```python
LT_MIN = 175
LT_MAX = 255
```

Then restart:

```bash
sudo systemctl restart xbox360-lt-fix.service
```

No systemd reload is necessary when only the Python script changes.

A `daemon-reload` is only necessary after editing the `.service` unit itself:

```bash
sudo systemctl daemon-reload
sudo systemctl restart xbox360-lt-fix.service
```

---

## Temporarily disable the workaround

Stop it:

```bash
sudo systemctl stop xbox360-lt-fix.service
```

Disable automatic startup:

```bash
sudo systemctl disable xbox360-lt-fix.service
```

Re-enable it:

```bash
sudo systemctl enable --now xbox360-lt-fix.service
```

---

## Remove the workaround

Stop and disable the service:

```bash
sudo systemctl disable --now xbox360-lt-fix.service
```

Delete the files:

```bash
sudo rm /etc/systemd/system/xbox360-lt-fix.service
sudo rm /usr/local/bin/xbox360-lt-fix.py
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

The physical controller will then behave exactly as it did before the workaround.


