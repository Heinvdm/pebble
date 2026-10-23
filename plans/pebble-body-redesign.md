# Body redesign: a real pebble that rights itself (plan only, not designed yet)

**Update, 17 October 2026:** the owner tried the pebble shell on the 12-motor Galaxy Flip hexapod instead (`new-bodies.md`, section 7b), then set it aside for now; the hexapod goes ahead bare, now carrying a normal phone (section 7a). The notes below were written for today's wheeled body and still apply if that body is reshaped later.

The owner's request, 17 October 2026: redesign the body so it is shaped like a pebble, and always rolls back onto its wheels if it falls over.

## Goal
- A smooth, rounded, pebble-like shell.
- Self-righting on its own like a roly-poly toy (a "weeble"): from any position it rolls back onto its wheels, with no help and no extra motor if possible.

## What the design has to solve (notes for later)
- **The physics.** A shape rights itself passively when its centre of mass sits low enough that, in every tipped position, the weight pulls it back towards upright. That means:
  - a rounded underside and back with a large radius;
  - the heavy parts as low as possible (the two 18650 cells, the motors, the UPS board);
  - the top light.
- **The phone is the hard part.** The Pixel 6 Pro weighs 210 g (about 245 g in a case) and sits high on the tilt mount, which raises the centre of mass. Options to compare:
  - keep the phone low and set back inside the shell's curve;
  - make the shell tall and round enough that the phone stays inside its righting envelope;
  - have the head tilt the phone flat when Pebble senses a fall (the phone's gyro and pebble-safety's fall detection already exist), to lower it before rolling back;
  - if passive righting can't work with a phone on top, add a small active assist using the existing tilt servo. Passive is the first choice.
- **The wheels** sit inside the shell's outline, so the round shell rolls cleanly and nothing snags. Ground clearance and carpet driving must still work. The current omni wheel may need rethinking, for example a hidden ball or a second pair of wheels.
- **Keep everything that works today:**
  - the sensors: the front distance sensor, the downward drop sensor (its 32° angle and footprint), and the bumper (perhaps as the shell's soft front);
  - both phone cameras' views, and the head tilt sweep;
  - docking on the charger: the pins and guide rails;
  - the battery hatch, the switch, the USB access.
- **Room for the safety chip** (see the agency plan, section 2b): a small board wired to the drop sensor, the bump switches and the motor driver's sleep pin.
- **Optional: a phone-charging switch** run by the ESP32, so Pebble can charge itself in its own rhythm (agency plan, section 3b).
- **Printability in PLA:** the shell may need to split into a top and bottom (or front and back) with inserts. Ballast pockets could hold extra weight low if needed, for example steel shot or washers.
- **Checks to add to the CAD tools:**
  - a centre-of-mass calculation from the real part weights;
  - a righting sweep that tips the model through every angle and confirms it always rolls back upright;
  - the existing collision, tilt, docking and sensor-cone checks.
- **Behaviour once it exists:** Pebble feels itself fall and roll back, and reacts ("Whoa! I'm okay."), using the existing fall detection. Its feelings and the alive system take it from there.

## What it will touch
- `cad/`: new shell, floor and parts, plus the righting check.
- `interfaces.md`: body geometry, sensor positions and docking.
- The parts list: possibly a different front wheel or ballast.
- The firmware: geometry and calibration constants only, if sensor positions move.
- The brain: the body profile (footprint for nav) and the fall reaction.

## When
After the navigation fixes and the agency plan, or whenever the owner wants it earlier. It can be designed and checked fully on the PC before anything is printed.
