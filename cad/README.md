# Pebble CAD

Parametric printable parts for Pebble, built with manifold3d in plain Python. Robot coordinates as in `../interfaces.md`: millimetres, origin on the floor under the middle of the axle, x forward, y left, z up.

## Rebuild

```
cd PhoneRobot\cad
.venv\Scripts\python.exe build.py              every STL into stl\, print orientation, on z = 0, with a size and gram table
.venv\Scripts\python.exe build.py neck_post    one part
.venv\Scripts\python.exe check.py              interference, tilt range, shell lift-off, docking, sensor cones, air vents, omni wheel, level, clearance, centre of mass, tilt servo load, the phone's rear lenses to the dock tag, the camera bar against the yoke
.venv\Scripts\python.exe assembly.py           all renders into renders\ (or: assembly.py views | details | omni | parts)
```

Change a number in `params.py`, run `build.py`, then `check.py`. Every part reads from `params.py`; nothing is typed twice.

## Files

| File | Role |
| --- | --- |
| `params.py` | every dimension and mass, grouped by class; derived values computed (tilt-axis height, omni position, bolt length, dock face, pin rows) |
| `geom.py` | primitives, extrusions, outline maths, tilt transforms and sweeps, STL writer |
| `dummies.py` | reference bodies: phone, servo, horn, motors, bought wheels, cells, boards, sensors and their view cones, switches, screws, springs, strips, magnets, pogo pins |
| `parts/*.py` | one module per printed part, each with `build()`, `PRINT` (rotation for printing) and `MATERIAL` |
| `assembly.py` | places parts and dummies, renders |
| `check.py` | all geometric checks and the centre of mass |
| `render.py` | numpy z-buffer renderer |

The yoke is cut by the swept MG90S envelope, and the neck post by the swept yoke, case plate and phone (tilt range plus 3 degrees, 1 mm clearance), so changing the phone or servo keeps them clear. The floor, shell and bumper are cut by the drop sensor's view cone plus 1 mm, and the floor and post by the front wheel's envelope plus 2 mm.

## Layout

- Drive axle at x = 0. Cells (holder 77 x 41 x 20) behind it, x -52.5 to -11.5, still loaded from below through the floor hatch.
- `electronics_shelf` over the cells (top at z = 37) on four floor pillars: HW-465A UPS and DRV8833. BMS on the floor beside the cells (y -58 to -50), 1000 uF cap behind them, ESP32-S3 at the rear wall with its USB-C in the slot as before. I2C runs about 180 mm along the floor to the two sensors at the front.
- Front: bought 58 mm omni wheel at x = 61.5 (as far forward as the front VL53L0X board allows with 2 mm clearance), in `omni_fork` on an M6 bolt. The neck post's front legs now land behind it at x 36 to 44 and are open where the wheel turns.
- Drop sensor pitched 32 degrees forward at x 92, y -31, z 27; its view leaves through notches in the floor's front edge, the shell's front wall and the bumper's bottom edge.
- Air sensor: `air_pod` on the floor against the LEFT side wall, x 45.6 to 69.4, between the shell boss at x 40 and the bumper's end at x 70.
  - The BME688 board stands upright in it, sensor facing the wall. In front of it are 6 vertical vent slots through the side wall (1.5 x 22 mm, z 16 to 38): 195 mm2 open.
  - The pod's back, sides and top wall it off from the robot's inside, so it breathes room air, not the warmth that pools under the shell top.
  - It sits 50 mm or more from the motor, the phone, the cells, the DRV8833 and the UPS (`check.py` prints the distances).

## Parts (all PLA)

| Part | Qty | Print orientation |
| --- | --- | --- |
| chassis_floor | 1 | as installed, underside on the bed |
| shell | 1 | rim down; tree supports under the top and under the 4 screw bosses |
| bumper | 1 | upright |
| front_sensor_mount | 1 | front face down |
| drop_sensor_bracket | 1 | upright |
| air_pod | 1 | upright, tabs on the bed; the roof bridges 18 mm, no supports |
| neck_post | 1 | upright (45 degree undersides, no supports) |
| tilt_yoke | 1 | socket opening up (phone "up" = print up) |
| case_plate | 1 | glue face down, tongue up |
| battery_hatch | 1 | outer face down |
| electronics_shelf | 1 | flat |
| motor_clamp_cap | 2 | flat |
| omni_fork | 1 | upright, feet down |
| wheel_hub | 2 | optional (only if not buying drive wheels); web face down; 2 O-rings 37 ID x 3 each |
| dock_base | 1 | flat, weight pockets underneath |
| dock_pin_block | 1 | upright; ream the pogo holes to 2.2 if tight |
| dock_wall | 1 | back face down |

Everything is PLA (density 1.24 in the gram table). The case plate and the yoke sit against the phone; if they creep from its heat, reprint those two in PETG.

## Bought parts to measure on arrival

| Part | Default | params.py |
| --- | --- | --- |
| Front omni wheel (Brompton-style, nylon, rubber rollers) | 58 dia, 26 wide, bore 6.2, hub boss 20 dia, hub faces 26 apart, 50 g | `Omni.d`, `width`, `bore`, `boss_d`, `face_to_face`, `mass` |
| Drive wheels for the 3 mm D shaft | 43 dia x 18 wide (`Wheel.bought = True`) | `Wheel.bought_*`; for the printed hub `Wheel.oring_*` |

Re-run `build.py` and `check.py` after entering them: the fork, floor slot, post legs and the 2 mm clearance follow.

## Hardware

- Heat-set inserts: M3 x 4 (shell bosses 4, post feet 4, hatch 2, bumper 2, yoke pin ear 1, shelf pillars 4, dock pin block 2, omni fork 4 pressed into the floor from below, flush), M2 (motor cradles 8).
- One M3 screw type: 20 x M3 x 8 countersunk (DIN 7991, 90 degrees, head 6 mm), every one sitting flush in a countersink: from below, shell to floor 4, post 4, hatch 2; from above, omni fork to floor 4, shelf to pillars 4; cell holder to hatch 2 (from below, with M3 nuts inside the holder). Under the floor nothing sticks out below z = 10.
- M2 under the floor: sensor brackets and air pod 6 x M2 x 6 countersunk self-tapping; switches 4 x M2 x 12 socket head + nuts, heads in counterbored slots.
- Front wheel: 1 x M6 x 45 bolt (a supplied M6 x 60 is 15 mm too long: cut it down) and an M6 nylock in the fork's hex pocket; the fork's printed spacers clamp only the wheel's hub boss.
- Motor caps: 8 x M2 x 6.
- Bumper: 2 x M3 x 25 socket head (the guide pins), 2 light compression springs about 5 OD x 10 long.
- Servo: snip the MG90S's front mounting tab; 1 servo screw through the rear tab into the post. Horn: 2 horn screws into the yoke plus the centre screw. Tilt pin: 1 x M3 x 12 through the yoke's pin-ear insert into the post's 3.4 bearing hole.
- Magnets 4 x 10 x 3 (glue, polarity marked); brass strips 30 x 4 x 0.5; 5 SMD pogo probes on perfboard.

## Measure before printing (where the number lives)

| Part | params.py |
| --- | --- |
| Phone in its case | `Phone.w`, `Phone.h`, `Phone.t` (axis height follows) |
| Phone's camera bar and rear lenses (Pixel 6 Pro: measured from a to-scale drawing, about ±1 mm) and how far the bar stands out of the case back | `Phone.bar_top`, `bar_bottom`, `bar_proud`, `lenses`, `bar_side` |
| MG90S body, tabs, shaft offset, spline | `Servo.*` |
| Servo horn disc, screw radius and angles | `Horn.*` |
| N20 gearbox, can, encoder, shaft | `Motor.*` |
| Cell holder outline and screw holes | `Cells.holder_*`, `Cells.holder_holes` |
| HW-465A UPS outline and holes | `UPS` |
| ESP32-S3 SuperMini outline, USB-C overhang | `Esp.*` |
| DRV8833, BMS, 1000 uF cap | `DRV`, `BMS`, `Cap.*` |
| GY-VL53L0XV2 board and chip offset | `Vl53.*` |
| BME688 board (Waveshare, 27 x 20 x 1.6), its tallest parts front and back, chip position | `AirPod.board_*`, `comp_front`, `comp_back`, `chip_dz`, `pcb_t` |
| Lever microswitch | `Switch.*` |
| Brass strip thickness, KCD11 cut-out | `ShellCfg.strip_t`, `ShellCfg.kcd_*` |
| Pogo probes, USB-C breakout | `Dock.pogo_*`, `Dock.usb_board` |
| Masses for the centre of mass | `Mass.*` |

## Assembly order

1. Press inserts. Fit motors and caps, cell holder to the hatch, ESP32, BMS and cap on the floor, UPS and DRV8833 on the shelf, then the shelf on its pillars; sensor brackets (slide the front VL53L0X down into its mount first), switches, bumper screws and springs.
   Air sensor:
   - Solder 5 thin wires into the BME688 board's VCC, GND, SDA, SCL and CS holes from the back. Bend them down behind the board.
   - Slide the board up into the pod's grooves from below, sensor side towards the open face, until it meets the roof.
   - Lead the wires out through the notch at the bottom of the back wall, set the pod on the floor and screw it from below. The floor now holds the board in.
   - Plug the notch around the wires with a dab of hot glue or Blu-Tack.
   - Optionally, stick a strip of 1 mm closed-cell foam on the pod's open rim so it seals against the shell wall.
2. Front wheel: set it between the fork cheeks, push the M6 bolt through, tighten the nylock until the hub boss is clamped and the rollers still spin, then screw the fork onto the floor.
3. Snip the servo's front tab, slide the servo under the post's hood until the rear tab meets the column, screw the tab. Screw the post to the floor.
4. Lower the shell over the post (bumper bosses and gearboxes go into its bottom notches), screw from below.
5. Screw the horn into the yoke, press the yoke onto the spline at the rest angle, fit the centre screw and the M3 pin.
6. Glue the case plate to the phone case (tongue vertical, centred), slide the phone down into the socket until the detent clicks.

To open: remove the yoke (centre screw, pin), then the 4 shell screws; the shell lifts straight up.

## Where this departs from interfaces.md

- Tilt axis x = 60, z = 132.26; clear from -43 to +95 degrees.
- MG90S front mounting tab snipped; the yoke is asymmetric (servo on +y, M3 pin on -y); case plate 26 x 50.
- Bumper gap and travel 2.5 (the shell is the hard stop); window 14 x 8; guide pins are M3 x 25 screws sliding in floor towers.
- Front support is a bought 58 mm double-row omni wheel, contact x 61.5, y 0, on an M6 bolt; it replaces the ball caster.
- Cells moved behind the axle (x -52.5 to -11.5); UPS and DRV8833 on a shelf over them; BMS beside them; ESP32 unchanged at the rear wall.
- Drive wheels can be bought (43 x 18, inner face at y = 76.5, centre y = 85.5) or printed (12 wide, centre 82.5, 2 O-rings).
- Drop sensor pitched 32 degrees forward at x 92, y -31, z 27; floor footprint x 100 to 120, rear edge 38.8 mm ahead of the omni contact; nominal reading on a flat floor 31.8 mm (calibrate `edge` from the real reading).
- KCD11 centre z = 54; ESP32 USB-C slot at y 23, z 17.3.
- Dock pins snapped to the 2.54 perfboard grid: y +-5.08, rows z 21.38 / 29 / 36.62. Tag centred z = 120. Dock 204 mm wide with the rail wings.

Grams in `build.py`: skin = surface area x 1.03 mm (3 walls x 0.42 and 4 x 0.2 mm layers, halved per face), capped at the volume, plus 20 % of the rest, times 1.24 g/cm3 (PLA).
