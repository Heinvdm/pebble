# Pebble — shared interfaces

Single source of truth for the numbers that the CAD, the firmware, the phone software and the build guide must agree on. If one of them needs a change here, change it here first.

The design spec was drafted in a private document that is not part of this repo. `reference/spec_snapshot_2026-10-15.txt` is a plain-text snapshot taken before the 2026-10-15 hardware changes; where it disagrees with this file, this file wins.

## Folders

| Folder | Contents |
| --- | --- |
| `cad/` | Parametric Python CAD (manifold3d), one script per part, shared `params.py`, `stl/` output, `renders/` previews |
| `firmware/` | ESP32-S3 SuperMini firmware, PlatformIO + Arduino framework |
| `brain/` | Phone-side Python software (the robot's mind and body drivers) |

## Coordinates

Millimetres. Origin on the floor under the middle of the drive axle. x forward, y left, z up.

## Body geometry

| Item | Value |
| --- | --- |
| Shell plan | Rounded rectangle 180 (x) × 150 (y), corner radius 38; front face x = +100, rear face x = −80 |
| Shell height | Top at z = 80; top edges rounded; walls 2.4 |
| Chassis floor | 3 mm plate, underside z = 10, top z = 13 |
| Drive wheels | Bought 43 × 19 mm rubber wheels (default 43 × 18 in the CAD), on the axle x = 0, centre z = 21.5, outside the shell, inner face y = ±76.5; printed 43 × 12 hubs with O-rings are the fallback |
| Motors | N20 with encoder, 12 (x) × 10 (z) gearbox, 34 mm long with encoder, gearbox face flush with the shell side (y = ±75), shaft 3 mm D |
| Front wheel | Bought 58 mm double-row omni wheel with rubber rollers on an M6 bolt in a printed fork, contact x = 61.5, y = 0, z = 0 (replaced the ball caster for carpet; width, bore and hub boss to be measured) |
| Cells | 2 × 18650 in a parallel holder about 77 × 41 × 20, long axis along y, behind the axle at x −52.5 to −11.5, loaded from below through a floor hatch |
| Electronics | UPS board and DRV8833 on a shelf over the cells (top z = 37); BMS on the floor beside the cells; 1000 µF behind them; ESP32 at the rear wall |
| Front distance sensor | VL53L0X looking forward at z = 40 through a bumper window |
| Drop sensor | VL53L0X pitched 32° forward, chip at x 92, y −31, z 27; floor footprint x 100 to 120, 38.8 mm ahead of the omni contact; reads about 32 mm on a flat floor |
| Air sensor | BME688 board upright in a printed pod on the floor against the left side wall, sensor facing out, chip at x 57.5, y 69.9, z 26.5; 6 vent slots 1.5 × 22 through the wall at x 50 to 65, z 16 to 38 |
| Bumper | Floating arc across the front, 2.5 mm gap, slides back 2.5 mm on 2 M3 × 25 guide screws with light springs, presses 2 lever microswitches |
| Power switch | KCD11 rocker (10 × 15 cut-out) in the rear wall above the dock pads |
| Dock pads | 3 horizontal brass strips on the flat of the rear wall, 30 wide × 4 tall: GND centre z = 22, DETECT centre z = 29, 5V centre z = 36 |
| Dock magnets | 2 × 10 × 3 mm discs in the rear wall at y = ±28, z = 29 |

Horizontal strips stacked by height make a sideways misalignment harmless: height is fixed by the floor, so a pin can never land on the wrong strip.

## Phone mount (any phone)

- Landscape phone in its own case, screen facing +x. A printed **case plate** (26 × 50) is glued to the back of the phone's case at its centre, clear of the rear camera, and carries a vertical dovetail tongue.
- The **tilt yoke** has the matching dovetail socket (open at the top, with a detent). The phone slides down into it: plug in, slide up to remove.
- The yoke's two ears straddle the servo and turn about a horizontal axis parallel to y, sitting behind the phone's centre. One ear screws to the MG90S horn, the other turns on a pin in a bearing hole, so the servo only steers.
- Tilt axis: x = +60, z = 132.26. Distance from axis to the back of the case: 15. This keeps the phone's weight close to the axis: its centre of mass is about 21 mm in front of it, so with the Pixel 6 Pro in its case (about 245 g) the servo holds about 0.53 kg·cm at rest and at most, about 30 % of an MG90S's 1.8 kg·cm stall torque (`cad/check.py`, plate and yoke included).
- Tilt range: clear from 43° down to 95° up in the CAD check (use −40..90). Resting position 8° up. With the selfie camera looking ahead and the rear camera looking behind (the dock's AprilTag), the tilt sweeps both views vertically.
- The **neck post** carries the servo cradle; the servo lies with its shaft along y and its body extending backwards from the axis, so the space under and in front of the axis is free for the phone's lower edge to swing back when looking down.
- Default phone used for clearances: 168 × 80 × 12 in its case (Pixel 6 Pro in a case). Axis height formula: shell top + 4 + √((15 + case thickness)² + (case height / 2)²).
- The phone is a Google Pixel 6 Pro (owner, 19 October 2026). The CAD also models its camera bar as a block standing 2 mm out of the case back (`Phone.bar_*` in `cad/params.py`; measure your case). Over the bar's span on +y the tilt yoke leaves only 1.5 mm behind the case back, so a bar standing out more than that must go on −y.

## Geometry as built (CAD 2026-10-15)

`cad/README.md` has the full list; these are the ones other parts of the project depend on.
- Tilt axis x = 60, z = 132.26; clear from −43° to +95° (`cad/check.py`). Set the firmware's `tmin`/`tmax` inside that range.
- The MG90S's front mounting tab is snipped off; the yoke is asymmetric (servo on +y, M3 pin on −y).
- Case plate 26 wide × 50 tall. Fit the phone so its rear camera sits in the UPPER half of the landscape phone, on −y if it can: on +y a camera within about 55 mm of the centre and less than about 20 mm above the centre line cannot see the dock's tag past the neck; on −y the yoke reaches only 28.5 mm out, and a camera 40 mm out sees the tag from 10 mm above the centre line (54 mm out, from 4 mm below it).
- The phone is a Google Pixel 6 Pro (163.9 × 75.9 × 8.9 mm, 210 g; about 245 g in a case). Its camera bar runs across the whole back, about 17.75 to 38.5 mm from the phone's top edge, and stands about 2.5 mm out of the back glass. The three rear lenses sit on the bar's centre line, 28.1 mm from the top edge; seen from the back with the phone upright, the wide (main) lens is 17.0 mm from the left edge (the side with the buttons), the ultrawide 31.8 mm and the telephoto 42.3 mm. (Measured from a to-scale drawing, about ±1 mm, until the phone is measured.)
- The camera bar goes on −y (Pebble's right; seen from behind, the bar is on the right and the lenses in its upper half). Mounted so, the lenses sit 53.9 mm from the middle and the wide lens 21 mm above the centre line (the ultrawide 6 mm above, the telephoto 4 mm below); all three see the whole tag (centre and corners) when docked at the rest tilt, about 180 mm away and 17.5° to the side, and the wide lens keeps the whole tag in its view from −11° to +33° of tilt. On +y the tilt yoke and the neck post block every lens, and a bar standing out more than 1.5 mm hits the yoke. Seen from the front, the phone's portrait top edge is then on the viewer's left: Android ROTATION_90 (plain landscape, the app's default). Checked by `cad/check.py` ("the phone's own rear lenses").
- Front support is a BOUGHT 58 mm double-row omni wheel (nylon, rubber rollers) on an M6 bolt in a printed fork, axle along y at x 61.5, z 29 (contact x 61.5, y 0, z 0). Its width, bore and hub boss are guesses until it arrives (`cad/params.py` `Omni`). It replaces the 12.7 mm ball caster in the table above.
- Cells moved BEHIND the axle: holder x −52.5 to −11.5, still loaded from below. UPS and DRV8833 sit on a shelf over the cells, the BMS on the floor beside them, the ESP32 stays at the rear wall (USB-C slot unchanged). I²C to the front sensors is about 180 mm.
- Drive wheels may be bought (43 × 18 on the 3 mm D shaft, centre y = ±85.5) or printed (12 wide, centre ±82.5, 2 O-rings 37 × 3).
- Drop sensor pitched 32° forward (looks down and ahead), chip at x 92, y −31, z 27; its floor footprint runs x 100 to 120, rear edge 39 mm ahead of the omni contact. Nominal reading on a flat floor 31.8 mm: calibrate `edge` from the actual reading. Front sensor position unchanged, board vertical. Front sensor window 14 × 8. Bumper gap and travel 2.5 mm.
- Rear wall: KCD11 centred at z = 54; ESP32 USB-C slot at y 23, z 17.3.
- Air sensor (BME688) sits in the printed `air_pod` on the floor against the LEFT side wall, ahead of the left wheel and behind the bumper's end. Pod x 45.6 to 69.4, y 60.2 to the wall (0.5 gap), z 13 to 42.3; 2 × M2 × 6 countersunk self-tappers from below at (48.3, 62.4) and (66.7, 62.4). The board stands upright (20 along x, 27 tall) with the sensor facing the wall, chip at about x 57.5, y 69.9, z 25 to 28. In front of it, 6 vertical vent slots go through the side wall (1.5 wide, z 16 to 38, at x 50, 53, 56, 59, 62 and 65): 195 mm² open. The pod is walled off from the robot's inside on its back, sides and top. Its only openings are the vents and a wire notch at floor level, where the inside air is coolest. The nearest heat sources are the left motor at 50 mm, the phone (at rest) at 70 mm, the cells at 74 mm, the DRV8833 at 84 mm and the UPS at 90 mm (`cad/check.py`).
- Dock pins snapped to the 2.54 mm perfboard grid: y ±5.08, rows z 21.38 / 29 / 36.62 (each at least 0.88 mm inside its strip).
- AprilTag centred at z = 120 (135 does not fit a 60 mm tag on the 150 mm wall). Dock 204 mm wide overall with the rail wings.
- The dock tag is tag36h11 id 0, printed 60 mm square including its white border, so the black square the eyes measure is 48 mm (`DOCK_TAG_SIZE_M = 0.048` in `brain/pebble/seams/sight.py`). The rear camera reads it at 1280 × 960: found out to about 2 m, yaw reliable within about 1 m.
- Everything is printed in PLA. Robot parts about 362 g of PLA with bought drive wheels; whole robot with the Pixel 6 Pro in its case (245 g, an estimate: 210 g plus about 35 g of case) about 940 g. Centre of mass x = 22.5 to 28.6 mm (ahead of the axle) over the whole tilt range; the front wheel carries 37 to 46 % of the weight. Every screw under the floor is countersunk flush, so the lowest point apart from the wheels is the floor underside at 10 mm.

## Microcontroller pin map (ESP32-S3 SuperMini, edge pins only)

| GPIO | Edge label | Signal | Notes |
| --- | --- | --- | --- |
| 1 | IO1 | Pack voltage (ADC1) | Divider 100 kΩ top / 100 kΩ bottom from pack + (after the BMS) |
| 2 | IO2 | Bump switches (ADC1 ladder) | 10 kΩ pull-up to 3V3; left switch to GND through 4.7 kΩ; right switch through 15 kΩ |
| 3 | IO3 | Right encoder B | Input |
| 4 | IO4 | Dock detect | Internal pull-up, 1 kΩ in series; the dock ties DETECT to GND, so LOW = seated |
| 5 | IO5 | I²C SDA | Both VL53L0X and the BME688 air sensor |
| 6 | IO6 | I²C SCL | Both VL53L0X and the BME688 air sensor |
| 7 | IO7 | Left encoder B | Input |
| 8 | IO8 | Tilt servo signal | 50 Hz |
| 9 | IO9 | DRV8833 AIN1 | Left motor |
| 10 | IO10 | DRV8833 AIN2 | Left motor |
| 11 | IO11 | DRV8833 BIN1 | Right motor |
| 12 | IO12 | DRV8833 BIN2 | Right motor |
| 13 | IO13 | Left encoder A | Input |
| 43 | TX | XSHUT of the DROP sensor | Output; boot chatter on TX is harmless here |
| 44 | RX | Right encoder A | Input |

- The FRONT sensor's XSHUT is left unconnected (on-board pull-up). At boot the firmware holds the drop sensor off, moves the front sensor to I²C address 0x30, then releases the drop sensor (stays at 0x29).
- Encoders and both VL53L0X are powered from **3V3** so their outputs are 3.3 V safe. Servo from the 5 V rail. DRV8833 nSLEEP/EEP tied to 3V3.
- I²C addresses on the one bus: 0x29 drop VL53L0X, 0x30 front VL53L0X (moved there at boot), 0x77 BME688 air sensor. No clash: the BME688 can only be 0x76 or 0x77, and the VL53L0X readdressing never touches either. The firmware tries 0x77 first, then 0x76. Each of the three boards brings its own pull-ups (typically 4.7 to 10 kΩ). In parallel that comes to roughly 2 to 3.3 kΩ, safely inside I²C's 3 mA limit at 3.3 V. Tap the BME688's SDA and SCL into the existing run near the front sensors, so no long stub hangs off the bus.
- Air sensor board (as built 2026-10-15): Waveshare "BME688 Environmental Sensor" (27 × 20 mm, onboard voltage translator, I²C or SPI). Header, in order: VCC, GND, SDA, SCL, ADDR, CS. Wire VCC to **3V3** (never 5 V; its bus side follows VCC), GND, SDA to IO5, SCL to IO6, and CS to 3V3 too: a CS pin floating low at power-up can latch the chip into SPI mode, and tying it high is harmless if the board already pulls it up. Leave ADDR open. Open (pulled high) gives 0x77; ADDR to GND (or the ADDR pad shorted) gives 0x76. Solder the five wires straight into the header holes from the back, with no header pins. A BME680 board also works: the same Bosch code handles it and only its gas formula differs.
- Logging and the bench link use native USB CDC, which leaves GPIO 43/44 free.

## Power

```
18650 ×2 (parallel) → 1S BMS → pack + ─┬→ HW-465A UPS board (5 V, 3 A) → power switch → 5 V rail → ESP32 5V pin, servo, phone lead (right-angle USB-C)
                                      └→ 2.5 A PTC fuse → DRV8833 VM → motors
dock 5V strip → HW-465A input (charges cells, powers the rail)
dock GND strip → GND; dock DETECT strip → IO4
```

- 1000 µF across the 5 V rail; 0.1 µF across each motor's terminals; all grounds common.
- Power budget, air sensor (on the ESP32's 3V3): the BME688 sleeps at about 0.15 µA between samples. Each sample is about 20 ms of temperature, pressure and humidity conversion (under 1 mA), then the gas heater at 320 °C for 150 ms, drawing up to about 12 mA (Bosch gives 0.09 to 12 mA, depending on mode). One sample every 3 s puts the heater at a 5 % duty cycle: about 0.6 mA average, with 12 to 13 mA peaks. The board's translator and regulator add well under 0.1 mA. Call it under 1 mA average, less than a single VL53L0X while ranging (about 19 mA), and nothing next to the motors or the phone.
- The switch (single-pole KCD11) cuts only the 5 V rail. With the ESP32 unpowered, the DRV8833's nSLEEP (tied to the ESP32's 3V3) drops and the driver sleeps, so the motors are dead too. The pack-to-UPS link is never switched, so it still charges when docked.

## Link protocol (firmware ⇄ phone)

Newline-terminated ASCII lines, at most 96 characters before a tag (a tag adds at most 25; see "The link key"). The same protocol runs over:
- USB CDC serial (bench, 115200). USB is trusted: whoever holds the cable may do anything.
- TCP port 7777 (ESP32 joins Pebble's own Wi-Fi, mDNS name `pebble.local`; one client). A new client replaces the old one only when the old one is unproven or has been silent for 2 s.
- BLE Nordic UART Service (device name `Pebble`; service 6E400001-B5A3-F393-E0A9-E50E24DCCA9E, RX write 6E400002-…, TX notify 6E400003-…), only while the pairing window is open (below). Otherwise Bluetooth is never started.

Phone → body:

| Line | Meaning |
| --- | --- |
| `D <l> <r>` | Drive, wheel power −1000..1000 per mille; ramped by firmware (max change 2000/s) |
| `M <l> <r>` | Closed-loop wheel speed in mm/s (PI on encoders; needs `cpm` calibrated) |
| `T <deg>` | Tilt target, clamped to `tmin..tmax` (default −35..90), slewed at most 120°/s |
| `X` | Stop all motion now and clear reflex holds |
| `P <n>` | Ping; replies `p <n>` |
| `Q` | Send one status line now |
| `C <key> <value>` | Set a setting in NVS (USB only); `C ?` lists all as `c <key> <value>` lines |
| `R` | Reboot (USB only) |
| `H <32 hex>` | Start the handshake with the phone's random number (any link) |
| `V <32 hex>` | The phone's proof (any link) |
| `K <64 hex>` / `K -` / `K ?` | Set or clear the link key (USB only); `K ?` answers `k set` or `k none` |

Only an accepted `D` or `M` refreshes the deadman; 500 ms after the last one the wheels stop. Resend the motion command while the wheels should turn.

As built (firmware 2026-10-15):
- `D`, `M` and `T` are silent on success and clamp out-of-range values; `X`, `C <key> <value>`, `C ?` (after its list) and `R` reply `ok`. Errors are `err <cmd> <reason>`: `<cmd>` is the command letter (`D M T X P Q C R`), or `?` when the line's first word is not one of those letters (lowercase and longer words included); `<reason>` is `unknown|syntax|long|cpm|key|value|range|nvs`. Examples: `err M cpm`, `err C key`, `err ? unknown`. An over-long line is answered with the letter it started with (`err D long`).
- `C <key>` with no value reads one setting back as exactly one `c <key> <value>` line and no `ok` (unknown key: `err C key`). `C ?` lists all nine keys in the order ssid, pass, cpm, edge, stop, tmin, tmax, trim, rest, then `ok`. An empty ssid lists as `c ssid -` and an empty password as `c pass -`; a set password lists as `c pass *`, never its text. Sending `-` as the value clears `ssid` or `pass`. Wi-Fi settings take effect after `R`.
- `E boot <version>` is sent to each link on its first connection after boot, not broadcast at boot.
- The deadman is motion-specific and replaces "any received line" above: only an accepted `D` or `M` refreshes it (an `M` refused with `err M cpm` does not); `P`, `Q`, `T`, `C`, `X`, `R`, malformed and over-long lines never do. 500 ms after the last accepted `D`/`M` the wheels stop and `E deadman` is sent once, if that command was still asking for motion; flag 32 stays set until the next accepted `D`/`M` or `X`. Resend `D`/`M` (for example every 200 ms) for as long as the wheels should turn. The tilt servo is unaffected.
- "Forward refused" clamps the forward component to zero; turning on the spot and reversing still work. Safety stops cut power instantly; normal commands ramp at 2000/s both ways.
- Low battery has hysteresis (clears above 3400 mV for 5 s); the 3100 mV cut clears above 3200 mV for 2 s.
- Any sensor fault refuses the wheels until the sensors recover, so on the bench the wheels stay refused with no pack or a sensor missing. The air sensor is NOT one of these sensors. When it is missing or failing, the `A` line says `none`, and no `E fault`, no flag 64 and no wheel refusal follow.
- BLE notifications can split a line; a dropped notification can leave a corrupt line, which the phone must discard. Once a link is proven every line carries a tag, so a corrupt line fails its tag and is dropped on both sides.

Settings keys and their bounds (firmware 2026-10-21; a value outside them is `err C range`, and a stored value outside them is replaced by the default at boot):

| Key | Meaning | Default | Allowed |
| --- | --- | --- | --- |
| `ssid`, `pass` | Wi-Fi network and password (the password lists as `*`) | empty | up to 32 / 8 to 64 characters, or `-` to clear |
| `cpm` | encoder counts per mm | 0 (unknown) | 0, or 5 to 60 |
| `edge` | drop threshold mm | 75 | 40 to 150 |
| `stop` | front obstacle mm | 60 | 30 to 300 |
| `tmin`, `tmax` | tilt limits, degrees | −35, 90 | inside −35 to 90, `tmin` below `tmax` |
| `trim` | servo trim degrees | 0 | −10 to 10 |
| `rest` | resting tilt, degrees | 8 | inside `tmin` to `tmax` (to narrow the tilt range, move `rest` first) |

Settings writes and key writes are limited to 4 a second (more is `err C busy`); a write that changes nothing answers `ok` without touching flash.

### Who may send what (firmware 2026-10-21)

| Link | Before the handshake | After the handshake |
| --- | --- | --- |
| USB | everything, untagged | every line tagged; an untagged line may only be `X`, `H` or `V` |
| TCP, BLE | only `X`, `P`, `H`, `V`; anything else is `err <letter> auth` | every line tagged (untagged: only `X`, `H`, `V`); `C <key> <value>`, `R` and `K` (except `K ?`) are `err <letter> usb` |

- `X` is always obeyed, from anyone: anyone may stop Pebble.
- Status (`S`), air (`A`) and events (`E`) go only to USB and to proven links. `E boot` goes to USB on connection, and to a network link when it is first proven after boot.
- A network link that has not proven the key within 5 s, or has failed the proof 3 times, is closed.
- New error reasons: `auth` (needs the handshake, or a bad or replayed tag), `usb` (USB only), `busy` (too many writes); `err H key` means the body has no link key yet.

### The link key, the handshake and tags

- A 32-byte key, set over USB only (`K <64 hex>`), kept in the ESP32's NVS, never listed. On the phone it lives in the Android keystore (alias `pebble-body-link`, StrongBox when the phone has it) and never leaves it; the admin screen's **Pair the body over the USB cable** makes it and sends it. On a PC, `python -m pebble.link.pair --serial <port>` makes it and writes `~/.pebble/link.key`; the brain uses it when `PEBBLE_LINK_KEY_FILE` names that file.
- Handshake: the phone sends `H <nc>` (16 random bytes, hex). The body answers `h <nb> <proof_b>`. Both work out `S = HMAC-SHA256(key, "pebble-link-1 <nc> <nb>")` (lower-case hex) and `proof_b` = the first 16 bytes of `HMAC-SHA256(S, "body")`, as hex. The phone checks it, so a body without the key can never pose as Pebble's body, then sends `V <proof_c>`, the first 16 bytes of `HMAC-SHA256(S, "phone")`. The body answers `ok` (or `err V auth`).
- After `ok`, every line both ways ends ` #<n> <tag>`: `n` counts from 1 in each direction and must always rise (gaps are allowed; a line with an old `n` is a replay and is refused), and `tag` is the first 6 bytes, as 12 hex digits, of `HMAC-SHA256(S, "<d><n> <line>")`, where `d` is `p` from phone to body and `b` from body to phone. Example: `D 300 300 #41 9c2e51ab07f3`. The longest command, `C pass` with 64 characters, still fits in 96 once tagged; lines from the body may reach 121 characters.
- A new `H` on any link drops that link's proof and starts again. Changing the key drops every network link.
- Test vectors (key bytes 0 to 31, `nc` = `00112233445566778899aabbccddeeff`, `nb` = `101112131415161718191a1b1c1d1e1f`): `S` = `c82d126e…a0f61cf1`, `proof_b` = `56ca065c618e088268640dc2628ad4c3`, `proof_c` = `5c97f3affe363f31e642b9d4d9dd7568`, the first phone line `D 300 300 #1 92edd70232c8`. The firmware (`test/test_link`), the brain (`tests/test_link_auth.py`) and the app (`BodyPairingTest`) all check them.

### The Bluetooth pairing window

Bluetooth is off in normal use. Hold the bumper in (either side) for 3 s while the wheels are still: the phone nods 10° and back, and the body advertises as `Pebble` for 2 minutes. It still obeys only a link that proves the key. The window stays open while a proven Bluetooth link is connected, and closes when that link ends or the 2 minutes run out with none. Holding the bumper longer does not open it again; let go and hold again.

### What the brain checks

At every link-up the brain reads `C ?` and refuses to drive the wheels (stop and tilt still work) when `cpm`, `edge`, `stop`, `tmin`, `tmax`, `trim` or `rest` is outside the bounds above, or the body does not list them. It tells the rest of the brain with a `fault settings` event of its own and says why in the brain log; the bounds are in `brain/pebble/body/checks.py`.

Body → phone:

| Line | Meaning |
| --- | --- |
| `S <ms> <encL> <encR> <front_mm> <down_mm> <bump> <dock> <pack_mV> <tilt> <flags>` | Status at 20 Hz. bump: 0 none, 1 left, 2 right, 3 both. dock: 1 seated. front/down: −1 when invalid |
| `A <ver> <ms> <temp_C> <humidity_%> <pressure_Pa> <gas_ohm> <heated_s>` or `A <ver> <ms> none` | Room air, field set version 1, about every 3 s; see Air sensor below |
| `E <name> [args]` | Event: `boot <version>`, `bump L|R|B`, `edge`, `obstacle <mm>`, `stall L|R`, `dock 1|0`, `lowbat <mV>`, `deadman`, `fault <what>` |
| `p <n>`, `c <key> <value>`, `ok`, `err <cmd> <reason>` | Replies |

Status flags bitfield: 1 edge hold, 2 bump hold, 4 obstacle ahead, 8 stall, 16 low battery, 32 stopped by deadman, 64 sensor fault, 128 reversing refused (a reverse was asked for with no reverse budget left; see Reflexes).

## Air sensor (BME688, firmware 2026-10-15)

`A 1 <ms> <temp_C> <humidity_%> <pressure_Pa> <gas_ohm> <heated_s>`, for example `A 1 123456 21.53 45.2 101325 152340 412`, or `A 1 <ms> none`.
- `1` is the field set version. `<ms>` is the body clock (the same clock as `S`) when the reading was taken; for `none`, when the line was sent.
- Temperature and humidity are decimals with up to 2 places, trailing zeros dropped (`21.5`, `-4`). Pressure is whole pascals.
- Gas is whole ohms, or `-1` when this reading's gas measurement is not valid (the heater didn't reach temperature, or the chip's valid flag is clear).
- `heated_s` is whole seconds since the sensor was started or restarted.
- `none` means one of two things: no sensor answered at 0x77 or 0x76, or 3 samples in a row failed. A sample fails on a bus error, on no new data in time, or on a value outside −40 to 85 °C, 300 to 1100 hPa or 0 to 100 %. It is sent every 3 s for as long as it lasts. The firmware probes again every 30 s, but only while the wheels are still. A recovered sensor starts again from `heated_s` 0.
- Compatibility: `S` is unchanged.
  - Adding fields at the end of a version is a compatible change: readers take the fields they know and ignore the rest.
  - Changing a field's meaning, unit or position takes a new version number, and a reader skips a line whose version it doesn't know.
  - Phones that predate `A` drop the line as malformed (the brain counts it in `LinkClient.malformed`) and carry on.
- Sampling uses forced mode with Bosch's open BME68x Sensor API v4.4.8 (BSD-3-Clause, vendored unchanged in `firmware/lib/bme68x`; not BSEC).
  - Oversampling is temperature ×2, pressure ×4 and humidity ×1, with no IIR filter. Then the gas heater runs at 320 °C for 150 ms. From trigger to data takes about 170 ms. One sample every 3 s.
  - A sample is not started while the wheels are driven, or within 200 ms of them stopping, so motor current and its supply ripple stay out of the measurement. It is held back at most 3 s more, so the worst case while driving is 6 s between readings.
  - Each step is one short I²C transfer, in the loop pass right after the 10 ms control tick, and no step waits. The only blocking is the 10 ms start-up soft reset: at boot, or after a dropout, and then only while the wheels are still.
  - The heater setting is recomputed when the room temperature has moved 5 °C from the value it was last computed for.

### Reading the numbers honestly (for the safety code and anything that talks about air)

- **Gas is a resistance, not a concentration.** It is the resistance of a heated metal-oxide layer, and VOCs, smoke, cooking fumes, alcohol and solvents lower it. It differs from one sensor to the next, drifts over hours and days, and moves with humidity and temperature.
  - Only a change against this sensor's own slow baseline means anything. Keep a baseline over tens of minutes (a median, or a slow average frozen while an event is going on) and watch the ratio gas / baseline.
  - There is no absolute "bad air" number. Readings can't be compared between sensors, or with published tables.
- **It cannot measure carbon monoxide.** There is no CO reading, and none can be worked out from the gas value. Pebble is not a CO alarm or a smoke alarm and must never say or imply that it is.
- **Temperature near the floor lags a fire.** The chip is 25 to 28 mm above the floor. Hot smoke and heat rise to the ceiling first, so a room can be dangerous while this still reads normal. A rise here is late evidence, never early warning.
- **The sensor needs a few minutes of warm-up after power-on or a restart.**
  - Temperature, humidity and pressure are usable at once.
  - Gas needs the heater cycling for a few minutes first: `heated_s` under 300 counts as warming.
  - The resistance keeps climbing for 10 to 30 min, so re-seed any baseline after a restart.
  - A brand-new sensor drifts over its first day or two of running (burn-in).
- Humidity jumps (shower, kettle, breath) move the gas reading too, so check humidity before blaming gas. Pressure follows the weather and altitude; it is not a hazard signal.
- **Self-heating.** The pod is walled off from the inside, and the chip is 50 mm or more from every heat source. But while docked and charging, the UPS and cells warm the body. Until this is measured on the real robot, treat a slow 1 to 2 °C rise while docked as the robot's own warmth.

Brain side:
- `pebble.link.protocol.Air` is the wire message.
- `pebble.body.sensors.AirReading` is kept as `Body.telemetry.air`. Its fields are `at`, `body_ms`, `present`, `temperature_c`, `humidity_pct`, `pressure_pa`, `gas_ohm` (None when not valid) and `heated_s`. It also has `pressure_hpa`, `warming`, `age(now)` and `fresh(now, max_age)`.
- `telemetry.air_reading(now, max_age)` returns a present reading, or None.
- The LLM sees `air` in `read_sensors`.

## Reflexes (firmware, never the LLM)

| Trigger | Action |
| --- | --- |
| Drop sensor reads beyond `edge` while moving forward or turning | Stop, reverse about 40 mm, edge hold: forward refused until `X` or a reverse command |
| Asked to reverse | Reverse power capped at 450. Net reversing only over floor just driven forward over: a reverse budget grows with straight or curved forward travel (counted on the encoders; at most 500 mm when `cpm` is set, else 10,000 counts) and shrinks as Pebble reverses; turning on the spot by more than 40 counts between the wheels empties it. With no budget, a reverse becomes a turn on the spot (or nothing) and flag 128 is set. The reflexes' own escapes (edge, bump) are not limited. |
| Bump switch | Stop, reverse about 30 mm, forward refused for 1 s |
| Front sensor below `stop` | Forward power clamped to 0; turning and reversing still allowed |
| Power above 300 with no encoder counts for 400 ms | Stop that wheel, `E stall`, hold 1 s |
| Pack below 3300 mV for 5 s | `E lowbat`, wheel power capped at 50 % |
| Pack below 3100 mV | Wheels refused |
| No accepted `D`/`M` for 500 ms | Wheels stop, `E deadman` once |

There is no rear drop sensor: the drop sensor looks forward and down only (32° pitch, footprint 100 to 120 mm ahead of the axle). That is why reversing is kept slow and limited to floor Pebble has just driven over. A rear cliff sensor (a second VL53L0X looking down behind the axle) would guard reversing properly; it needs a pin for its XSHUT and a place in the CAD.
