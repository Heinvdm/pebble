# Pebble body firmware

Firmware for the ESP32-S3 SuperMini that drives Pebble's wheels, tilt servo and sensors and runs the safety reflexes. Pins, power wiring, the link protocol, settings keys and the reflex table are in [../interfaces.md](../interfaces.md); this firmware implements that file.

Platform: PlatformIO `espressif32 @ 6.13.0` (Arduino core 2.0.17), board `esp32-s3-devkitc-1` set to 4 MB QIO flash, 2 MB quad PSRAM, USB CDC on boot.

## Build, flash, test

From this folder (Windows paths shown; use `.venv/bin/` on Linux or macOS):

```
python -m venv .venv
.venv\Scripts\pip install platformio
.venv\Scripts\pio run                  # build
.venv\Scripts\pio run -t upload        # flash over the USB-C port
.venv\Scripts\pio device monitor       # serial terminal, Enter sends a line
.venv\Scripts\pio test -e native       # unit tests on the PC
```

If the port does not appear, hold BOOT while plugging the board in, then upload again. On Windows without a gcc on PATH, the native tests fetch PlatformIO's MinGW toolchain (about 100 MB) on first run.

## Wi-Fi, the link key and Bluetooth

Settings, the Wi-Fi password, the link key and a reboot are taken only over the USB port. To add Wi-Fi (Pebble's own network, not your main one; `android/SETUP.md` step 3), send over USB:

```
C ssid PebbleNet
C pass the-wifi-password
R
```

After the reboot the body joins the network and listens on `pebble.local:7777`. `C ssid -` clears the network, `C ?` lists every setting (the password shows as `*`).

Over Wi-Fi and Bluetooth the body obeys only a phone that proves the shared link key (`interfaces.md`, "The link key, the handshake and tags"); anyone may still send `X` to stop it. Give it the key from the phone (admin screen, **Pair the body over the USB cable**) or from a PC:

```
cd ../brain
.venv\Scripts\python -m pebble.link.pair --serial COM5
```

That makes a key, sends it with `K <64 hex>`, checks the body proves it, and saves it to `~/.pebble/link.key` (set `PEBBLE_LINK_KEY_FILE` to that file for the brain on the PC). `K ?` answers `k set` or `k none`; `K -` forgets the key. Flashing the firmware keeps the key (it lives in NVS); erasing the flash loses it, and then the body must be paired again.

Bluetooth is off. Hold the bumper in for 3 seconds while the wheels are still: the phone mount nods, and the body advertises as `Pebble` for 2 minutes, for a PC on the bench (`ble:Pebble` with the key file set). It closes when that time runs out with no proven link, or when the proven link ends.

## Bench test

Open any serial terminal on the board's USB port (`pio device monitor` works) and type:

| Send | Expect |
| --- | --- |
| `P 7` | `p 7` |
| `Q` | one `S ...` status line; status also streams at 20 Hz |
| `T 30` | the phone tilts back to 30°, at most 120°/s; `T 8` returns to rest |
| `D 300 300` | wheels turn for half a second, then `E deadman`; only resending `D` (or `M`) keeps them going, pings do not |
| `X` | `ok`, everything stops and reflex holds clear |
| `C stop 80` | `ok`; the front obstacle distance is now 80 mm (30 to 300 allowed; `C stop 0` is `err C range`) |
| `K ?` | `k set` or `k none` |
| `D -300 -300` right after power-on | nothing: the reverse budget is empty until it has driven forward (flag 128 in `S`) |
| (wait 3 s) | `A 1 <ms> <temp_C> <humidity_%> <pressure_Pa> <gas_ohm> <heated_s>` every 3 s, or `A 1 <ms> none` with no air sensor |

Status: `S <ms> <encL> <encR> <front_mm> <down_mm> <bump> <dock> <pack_mV> <tilt> <flags>`. Press the bumper, cover the front sensor or lift the robot to watch `bump`, `front_mm`, `down_mm` and the flags change.

The air sensor is the exception: without it the wheels still run and only the `A` line changes, to `none`. Breathe on it or hold a marker pen near the vents to watch `gas_ohm` fall. It is `-1` until the heater has reached temperature.

The wheels stay refused, by design, when a distance sensor is missing (`E fault front` or `E fault drop`) or when no pack is connected (the pack reads 0 mV, `E lowbat 0`). D, M and T reply only on error; X, C and R reply `ok`.

## Layout

- `lib/pebble_core/` hardware-free logic, unit tested on the PC: protocol parsing and formatting, line assembly, reflex state machine, drive shaping (ramps, speed PI), tilt slew, bump ladder, settings validation.
- `lib/bme68x/` Bosch Sensortec's BME68x Sensor API v4.4.8 (BSD-3-Clause, `LICENSE` beside it), copied unchanged from github.com/boschsensortec/BME68x_SensorAPI (commit 80ea120a). This is the open API, not the proprietary BSEC library: it gives raw temperature, humidity, pressure and gas resistance, and no "air quality index".
- `lib/pebble_air/` the BME688 air sensor behind a small bus seam (`AirBus`), so the same code runs on the PC.
  - It finds the sensor at 0x77 or 0x76, then sets forced mode with a 320 °C, 150 ms heater step.
  - It samples every 3 s and never waits in the loop. While the wheels move it holds a sample back, by 3 s at most.
  - It refuses out-of-range readings. After 3 failures in a row it reports `none` and probes again every 30 s.
- `src/` the ESP32 side: motors (DRV8833, 20 kHz slow decay), encoders (PCNT), VL53L0X pair, the BME688 on the same I2C bus (`air_bus.cpp`), bump ladder, pack voltage, dock, servo, NVS settings, USB/TCP/BLE links and the main loop (`robot.cpp`).
- `src/config.h` pins and every constant that needs calibrating on the real robot (motor and encoder directions, servo direction and pulse range, pack calibration, air sample timing and heater step).
- `test/` Unity tests for `pebble_core` and `pebble_air`. `test/test_air` drives Bosch's code through a fake BME688 register map:
  - Its calibration words and raw temperature, pressure and humidity words were recorded from a real BME680 (pimoroni/bme680-python issue #11). The reference results there come from Bosch's integer maths: 26.69 °C, 98712 Pa, 42.40 %. The temperature, pressure and humidity maths is the same on the BME688.
  - Its gas word is made up: BME688 high range, range 9, ADC 712, which works out at 109029 Ω.
  - Once the real board is running, swap in a dump from it: registers 0x8A to 0xA0, 0xE1 to 0xEE and 0x00 to 0x04, plus one field block from 0x1D to 0x2D.
