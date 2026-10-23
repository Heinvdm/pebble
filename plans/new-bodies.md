# New bodies: Pebble learns a body it has never seen (future plan, not built)

The owner's question, 17 October 2026: if he builds another body with different motors and sensors and connects Pebble to it, without coding the movements in a simulation first, could Pebble learn it by itself? It might use pictures of the body, or sense which parts are there, then write the ESP32 code, test until it knows how to use the body, and store that so it can have different bodies.

**Short answer: yes, in stages.** The mind, memories and personality live in the phone, so Pebble stays Pebble in any body, like a hermit crab changing shells. What changes is a "body profile" it learns and keeps.

## 1. Knowing what it's in
Four sources, used together:
- **A body ID chip (recommended, about NZ$1).** Each body carries a tiny memory chip (an I2C EEPROM) holding its name. Pebble writes what it learns back into it, so plugging in a known body is instant. This is how Raspberry Pi add-on boards identify themselves.
- **Pictures.** Before connecting, Pebble looks at the body with its camera: wheels, legs, servos, an arm, where the sensors point. The owner can add words ("the left servo is the arm").
- **Sensing the wiring, carefully:**
  - It scans the I2C bus; common sensors have known addresses (distance, motion, air, light).
  - It listens on serial lines and reads analogue pins.
  - Outputs are only tried with tiny, brief pulses. Driving an unknown pin can damage hardware, so the owner gives a simple wiring card (a photo or a short file) for anything that isn't on a bus.
- **A general "explorer" firmware first.** Instead of writing new firmware blind, Pebble starts with a general firmware that just exposes the pins, buses and timers to it (like Firmata). Once it understands the body, it writes proper firmware for it, with the backups, two slots and rollback from the agency plan, section 2b.

## 2. Learning to move it ("motor babbling", like a baby)
- **Gentle first:**
  - wheels off the ground, or the body on a stand, for the first session;
  - low power caps;
  - one part at a time.
- **Watching what happens.** Pebble sends small commands and watches the result with:
  - the phone's gyro and accelerometer;
  - camera motion (how the world shifts);
  - any encoders, and its own distance sensors;
  - a mirror, or the owner holding a second view, if it helps.

  From that it learns which command does what: this servo lifts the arm, this motor turns left, this much power gives this speed.
- **Its own sim of the new body.** From what it learned, it builds a simple model of the body and practises in it overnight ("dreaming movement"). Then it tries the best moves for real and corrects the model. This is the idea behind self-modelling robots (Columbia's work on robots that learn their own bodies) and trial-and-error adaptation (Cully et al., 2015).
- **Skills built from the basics:** driving straight, turning, stopping, then whatever the body allows: walking gaits for legs, reaching for an arm. Gaits are tuned as a few rhythm settings (step timing, height, phase), which the phone can optimise. No huge training is needed.
- **Honest limits:**
  - wheels and simple servos take minutes;
  - legs and arms take hours or days of practice and some wear on parts;
  - it may ask for help ("Can you hold me up while I try my legs?").

## 2b. The owner's way: teach it, then let it practise (owner's notes, 17 October 2026)
- **First, before any connection:**
  - the owner fits a safety chip in each new body;
  - Pebble trains on the laptop in a simulation of the body;
  - only then is it connected.
- **A guided tour, later.** The owner carries Pebble round the new body and tells it about each sensor and part ("this is the rain sensor", "this servo is the left leg"). Pebble ties the words to what it sees.
- **Teaching by hand.** With Pebble connected, the owner moves each actuator to its limits by hand while talking to it. Pebble records the limits and the feel of each joint.
  - Plain hobby servos can't report their position, so Pebble watches them with its camera. Smart servos that report their position (Feetech STS-type) make this precise.
- **Then it carries on alone,** testing and learning by itself within those limits, as in section 2.

## 3. Storing and switching bodies
- Each body gets a profile in its self, `mine/bodies/<name>/`:
  - photos and the parts list;
  - the wiring and the learned model;
  - firmware versions and calibrations;
  - skills, limits, and how it "feels" to be in it.
- When connected, Pebble reads the ID chip and loads the profile, so it knows the body at once. If the body is unknown, it starts learning mode and says so.
- Navigation, safety and personality adapt to the body's size, speed and senses. It might say "I'm in my tall body today."

## 3b. Any ESP32 gadget: "Pebble, change this for me"
An idea from the owner: connect Pebble to any ESP32 that already has its own sensors and code, a weather station for example, and ask it for changes.

- **The catch:** an ESP32 holds only the compiled program, not the source code, and that can't practically be turned back into editable code. So:

| What's on the gadget | What Pebble does |
| --- | --- |
| The owner's own code, with the source given (a folder or GitHub link) | Edits, builds and flashes it |
| ESPHome, Tasmota or WLED | Changes their settings and scripts directly; their configuration lists the sensors |
| Someone's compiled code, no source | Backs up the original. Finds the sensors (bus scan, its serial, web or MQTT output, photos, the owner's words). Writes a new program that does the same job plus the change. Checks the readings match before switching over. |
| Locked (flash encryption or secure boot) | Can't be read or changed, by design |

- **Connection:** over Wi-Fi when the gadget allows remote updates (most hobby firmware does), otherwise a USB cable from the phone or laptop.
- **Manners:**
  - it only touches gadgets the owner points it at;
  - it backs up the full flash first, says exactly what it will change, and waits for a yes;
  - it keeps every version and restores the original on request or if the new one misbehaves.
- **Builds on:** the compile path and backups in the agency plan, section 2b, and the discovery tools in section 1 here.

## 4. Safety in any body
- **Law 1 holds in every body.** Learning mode only runs when no person or animal is within reach of the moving parts. It stops instantly on "stop", a bump or a fault.
- **Each body needs its own safety layer, owner-built.** A safety chip like the one in agency plan section 2b, matched to that body:
  - edge and bump stops for anything that drives;
  - current limits, and a physical stop button for strong parts like arms.
- **Power:** new actuators can draw more than the board allows, so learning starts with low current limits and raises them only as far as the body's power supply allows.

## What it needs from today's plans
- The agency plan's own code, ESP32 freedom (section 2b), drives and feedback loop. This builds directly on them.
- Pebble's navigation and body profile, made per body instead of fixed.

## When
After the agency plan and the pebble-body redesign. Today's body can be the first test: Pebble re-learns it from scratch and is compared with the hand-written firmware.

## 5. Extended senses and limbs on the network (owner's idea, 17 October 2026)
The owner gives Pebble the spec files and pinouts for a Raspberry Pi or ESP32 project, a weather station for example, plus photos and a few words. Pebble sets the device up completely, connects it to the home Wi-Fi, and from then on uses it as an extra sense or limb.

- **Giving it the files:** the Wi-Fi inbox (agency plan, section 2).
- **Are spec files enough?** Mostly, yes, if they name:
  - the board;
  - each part (model number);
  - which pin each part is wired to;
  - how it is powered.

  Pebble checks the files against reality before trusting them: an I2C scan should show the expected addresses, the readings should be sensible, and the photos should match the wiring. If something doesn't match, it asks.
- **ESP32:**
  - The first flash needs a USB cable, from the laptop, or from the phone once the body has a USB slot. Firmware that already allows remote updates can be flashed over Wi-Fi.
  - Pebble's firmware includes Wi-Fi, reporting to Pebble (MQTT or HTTP) and over-the-air updates, so every later change goes over the air, with backups and rollback.
- **Raspberry Pi:**
  - One manual step: writing the operating system to the SD card with Raspberry Pi Imager. Pebble prepares the settings (Wi-Fi, a login key) for the owner to paste in.
  - After that, Pebble does everything over SSH: turning on I2C or SPI, installing packages, writing the program, starting it on boot, and locking it down. That means a key login only, updates on, and nothing open to the internet.
- **Wi-Fi password:** the owner tells it once, and it is sealed with the rest of its self. Android doesn't let apps read saved Wi-Fi passwords.
- **No internet, no cloud** (owner, 17 October 2026): everything comes from Pebble's own offline stores. See `plans/workbench.md`.
- **Once running:** each device gets a profile in `mine/bodies/` ("garden weather station"), and its readings become one of Pebble's senses. Pebble watches its health and can update it.
- **Limbs that could hurt** (heaters, locks, pumps, mains switches, garage doors): the owner approves each device, and every action goes through the gatekeeper and law 1.

## 6. Can Pebble's own model write this code?
- **Today:**
  - The main model (Gemma 4 E4B, on the phone) runs with a 4,096-token window, about 3,000 words. That's set by Pebble's model profile (`-c 4096`), not by the model: it supports much longer windows, and the limit on the phone is memory.
  - It also shares the phone with speech, vision and depth.
- **What a job needs:**

  | Part of the job | Tokens |
  | --- | --- |
  | A weather-station sketch using sensor libraries (150–400 lines) | 2,000–5,000 |
  | Instructions and laws | about 1,000 |
  | The relevant pins and spec lines | 1,000–2,000 |
  | Compiler errors | small |

  So about 8,000–16,000 tokens for a single-file job. A whole datasheet (often 50,000+ tokens) never fits.
- **How to make it work on the phone:**
  1. A larger window for coding jobs only, for example 16K, run when Pebble is idle or docked. Measure the Pixel 6 Pro's memory and heat first (with 12 GB the window's own memory is small, about 0.3 GB at 16K by the model's published layout; heat is the likelier limit).
  2. Work in small pieces: one file or function at a time, edited as replacements rather than rewritten whole. A project notes file in `mine/` carries the overall picture between steps.
  3. Search spec files instead of reading them whole: chunk and index them, then pull only the pin tables and registers needed.
  4. Lean on well-known sensor libraries, so there's less code to write.
  5. Keep its own recipe book of code that worked and reuse it. It gets better with every project.
  6. A tight loop: compile, feed back only the error lines, fix, flash, check readings.
- **Speed (estimate, to measure):** reading a 16K prompt takes a few minutes on the phone, and writing 400 lines another 5–10 minutes. That's fine overnight or while docked; the phone gets warm.
- **Honest quality limit:**
  - A 4B-class model handles small, well-described jobs with libraries.
  - Setting up a whole Pi, or writing tricky firmware from scratch, needs many tries or a stronger model.
- **No laptop helper or cloud model** (owner, 17 October 2026): Pebble does it all on the phone. A better phone later lifts the limits. Tools and approach: `plans/workbench.md`.

## 7. A mini hexapod body for a Galaxy Flip (owner's decisions, 17 October 2026)
The owner's idea: Pebble in a Galaxy Z Flip, on a mini hexapod that can run quickly, jump and turn, using as few motors as possible for the same effect.

**Latest decision (owner, 18 October 2026): the 12-motor version, bare, carrying a normal phone in today's tilting head.** See section 7a. The Flip is set aside because Pebble's kiosk mode can't be relied on on its cover screen. A pebble-shaped shell was designed and then set aside for now (7b). This section records how the design got there; where they differ, 7a wins.

**Decided:**
- The folded Flip stands upright in a small cage in the middle of the body.
- Six legs that run, jump and turn. **No walking sideways** (the owner cancelled it).
- **As few motors as possible** for the same effect.
- Brushless motors, each with a magnetic encoder and FOC control.
- **Power comes from the phone's USB-C port,** not wireless.
- **Each leg has mechanical limits,** so it never flops around.
- **When still, it sits all the way down** on its belly, with no power to the motors until it moves again.

**Looked at and set aside:**
- 18 motors (three per leg): only needed for walking sideways.
- Two motors per leg (12), including five-bar legs: the linked design below does the same job with four.
- One motor per leg (RHex-style spinning legs).
- Wireless power from the phone: 4.5 W at most, and it heats the phone.

### The trick: legs that move together share a motor
When a hexapod runs, it uses a tripod gait. Three legs are down while the other three swing forward, then they swap:
- tripod A: left front, right middle, left back;
- tripod B: right front, left middle, right back.

The legs in each group move together anyway, so they can share motors through linkages. Four motors are enough:

| Motor | Moves | What it gives |
| --- | --- | --- |
| Left swing | The three left legs, forward and back. The middle leg swings opposite to the front and back legs, through a reversing link. | Walking and running on the left side |
| Right swing | The same for the three right legs | Walking and running on the right side |
| Lift A | Raises and lowers the three legs of tripod A | Stepping, standing, sitting, jumping |
| Lift B | Raises and lowers the three legs of tripod B | Stepping, standing, sitting, jumping |

### How it does each move
| Move | How |
| --- | --- |
| Walk and run | Lift A and Lift B take turns while both swing motors stroke. Faster strokes mean faster running. |
| Turn | The two sides swing at different speeds, like a tank. On the spot, one side strokes forwards and the other backwards. The front and back feet scuff a little as it turns, which rubber feet handle. |
| Jump | From a crouch, Lift A and Lift B push all six legs down at once, mostly straight up. Swinging both sides back during the push adds a short forward hop: the middle legs, linked in reverse, sweep forward, so four legs push back against two. Opposite swings make a small turning hop. |
| Land | Both lift motors act like springs and soak up the landing. |
| Sit and rest | Both lift motors raise every leg, so the body settles onto its belly. Then the motors switch off and the legs rest against their stops. |
| Lean sideways | Pushing one tripod harder than the other rolls the body a little. |
| Look up and down | The linked legs can't tilt the body forwards or back, so the phone's cage gets a small tilt servo, like today's yoke. |

### The legs
- **Hip:** each leg swings forward and back about a vertical hip axis, about ±25°.
- **Thigh:** it lifts the leg about a horizontal axis.
- **Shin:** held upright by a parallelogram link, so lifting moves the foot almost straight up and down. That's good for stepping and gives a straight push for jumping. It still looks like an insect's leg.
- **Linkages:**
  - the swing push-rods run along each side;
  - the lift links cross under the belly to their three legs;
  - each lift link's inner ball joint sits on the leg's swing axis, so swinging the leg doesn't change its lift.
- **Hard stops with rubber bumpers** on the swing and lift of every leg:
  - they set the limits;
  - they take landing shocks;
  - they hold the legs tidy at rest;
  - they tell Pebble where the legs are: on waking, each motor pushes gently into a stop to find its true angle.
- **Feet:** soft rubber tips for grip and quieter steps.
- **Rough sizes:** thigh 45 mm, shin 60 mm. Standing, the legs span about 25 cm.

### The four motors
Fewer, bigger motors are easier than many tiny ones. A bigger motor gives more torque per watt and per gram, is easier to buy, and needs only a simple one-stage gearbox. The 11 g actuator that the 18-motor design needed is no longer the hard part.

All torques are estimates for a robot of about 580 g:
- **Lift motors (the strong ones):**
  - about 0.3 Nm steady, since one lift motor carries the whole robot while its tripod is down;
  - about 0.5 Nm peak for jumps and landings;
  - a 28–35 mm gimbal-class motor with a 6–10:1 single-stage gearbox.
- **Swing motors (the fast ones):**
  - about 0.1–0.15 Nm, mostly for pushing forward and scuffing round turns;
  - the same motor size or smaller, geared for speed.
- **On every motor:**
  - a magnetic encoder (MT6701 or AS5047P);
  - FOC control with current sensing;
  - a current limit, which is also a torque limit.

### Electronics
- **One motor board** runs all four motors, with a microcontroller made for motor control (STM32G4 class).
  - It runs each motor's current about 20,000 times a second and each joint's springiness 1,000–5,000 times a second.
  - It also enforces the current caps and stops, and watches heat.
- **The main board:**
  - an ESP32-S3, linked to the phone over USB;
  - its own fast motion sensor (IMU) for balance and landings;
  - the battery manager;
  - the cage's tilt servo.
  - It runs the gait engine 500–1,000 times a second.
- **The safety chip** (section 4) cuts the motor drivers on a tip-over, a drop edge or a lost heartbeat.
- **Joints act like springs.** Each motor is told a target angle, how stiff to be, how much damping, and an extra push. Landings are absorbed, and a leg touching something is felt through the motor current.

### Who decides what
| Level | Runs on | How often | Does |
| --- | --- | --- | --- |
| Pebble's mind | Phone | When it decides | Where to go, which way to face, "hop onto the cushion" |
| Motion commands | Phone → body over USB | 50–100 a second | Speed, turn rate, body height, gait, head tilt, "jump now" |
| Gait engine and balance | Main board | 500–1,000 a second | Which tripod is up, stroke timing, keeping level, landing |
| Motors | Motor board | 1,000–20,000 a second | Current, springiness, stops, current caps, heat |

The reflexes (stop, sit, land, drop edge) live on the body, so they never wait on the phone.

### Power: USB as the supply, a small battery for the bursts
- **Running and jumping need short bursts** far beyond what a phone's USB port gives. A jump might take 20–40 W for a tenth of a second.
- **So the body carries a small high-discharge battery** (2S, about 300 mAh, about 18 g). The phone's USB charges it, and the battery delivers the bursts. USB is the supply; the battery is the muscle.
- **Using it:**
  - four motors waste less power than twelve or eighteen small ones, so a charge goes further;
  - at rest, the motors and drivers are off and the chips asleep;
  - losing power always ends in the rest pose: the legs go limp and the body drops onto its padded belly.
- **Still to measure:** how much power the Flip's USB-C port gives out. The USB limit for a basic port is 500 mA; USB-C can offer more.
- **Still to solve: charging the phone on the dock,** since its only port is taken by the body. Either:
  - the dock charges the phone wirelessly through the back of the cage (the Flip takes 15 W), if it keeps powering its USB port while it does; or
  - the body passes the dock's power through to the phone.

### The body, the cage and the phone
- **The phone:** the Flip 7 folded is about 85.5 × 75.2 × 13.7 mm and 188 g. It stands hinge up, with the USB-C plug at the bottom.
  - It sits low, its bottom level with the belly, to keep the centre of mass down for turns and landings.
  - The cage carries the phone; the plug floats, so it never holds the phone up. A loop of cable lets the cage tilt.
- **The face:** the cover screen and the main cameras face forward. Check that the kiosk app can run full-time on the cover screen (Samsung limits it; Good Lock's MultiStar is the usual way round that).
- **Bumpers:** a ring round the cage protects the phone. Jump height is capped at what the cage survives in drop tests.
- **Weight (estimate):**

  | Part | Grams |
  | --- | --- |
  | Flip | 188 |
  | 4 motors with encoders and gearboxes | about 200 |
  | Linkages, legs and feet | about 60 |
  | Body, cage and belly | about 50 |
  | Tilt servo | about 13 |
  | Motor board, main board and IMU | about 20 |
  | Battery | about 18 |
  | Wiring | about 10 |
  | **In all** | **about 560–580** |

  Today's body is about 920 g.

### What it should do (targets to prove, not promises)
- **Run:** 0.5–1 m/s, at 5–8 steps a second.
- **Turn:** on the spot, or while running.
- **Jump:** about its own height, 5–8 cm, up or forwards.
- **Rest:** close to no power.

### What it gives up for using four motors
- **Rough ground:** the legs of a tripod move together, so they can't each find their own footing. Soft feet and a low body help; it is a floor and table robot.
- **Tilting forwards and back:** the linked legs can't do it, hence the tilt servo.
- **Spare legs:** a jammed linkage stops a whole tripod, not one leg.
- **If these matter later:**
  - **8 motors:** one lift motor per leg, plus the two swing motors.
    - Each lift motor sits on its hip and swings with the leg, turning the thigh directly. Each could instead sit in the body with its own link, which keeps the legs light but adds six links.
    - **What it brings back:**
      - body tilt: the legs lean the body up to about 12°, so the phone needs no tilt servo;
      - footing on rough ground;
      - reflexes for each leg.
    - **What stays the same:** the gait is still tripod, because the swing stays linked, and the jump is about the same height, with six smaller motors sharing the push.
    - **Costs (estimates):**
      - each lift motor needs about 0.1 Nm steady and 0.2 Nm peak;
      - about 270 g of motors against 200 g, about 630–650 g in all;
      - 2 or 3 motor boards;
      - legs that swing a little slower, since the lift motors ride on them.
  - **12 motors, on a power bank** (owner's idea, 17 October 2026): a swing motor and a lift motor on every leg, with no links between legs.
    - **What it adds over 8:**
      - any gait, including creeping one leg at a time on rough ground;
      - turning on the spot with far less scuffing;
      - full forward hops, since all six legs can sweep back together.
    - **Still no walking sideways;** that needs three motors per leg.
    - **The motors' power: a Xiaomi UltraThin Magnetic Power Bank 5000** (MDY-20-EB):
      - 98.5 × 71.5 × 6 mm and 98 g;
      - 18.95 Wh in the cell, rated 3,000 mAh at 5 V;
      - USB-C out at 5 V 3 A or 9 V 2.5 A (22.5 W);
      - 15 W magnetic wireless out.
    - **How it's used:**
      - it lies flat in the belly, wireless face down, under the phone;
      - the body asks it for 9 V over USB-C;
      - the firmware keeps the total under 2.5 A;
      - supercapacitors (four 10 F cells, about 15 g) cover the jump's 40–60 W push.
    - **The phone:** it keeps its own battery for thinking, and its USB cable to the body carries data only.
    - **Estimates:**

      | | |
      | --- | --- |
      | Usable energy | about 14 Wh |
      | Walking | 5–10 W, 1.5–2.5 h |
      | Running | 15–20 W, about 45 min |
      | Standing | about 3 W |
      | Each lift motor | about 0.13 Nm steady, 0.35 Nm peak |
      | Motors in all | 300–360 g |
      | Whole robot | about 850–920 g |

    - **Still to solve:**
      - **Auto-off:** the bank switches itself off when almost nothing is drawn. The body wakes it by replugging it electronically, with a switch on the USB-C line. Test this with the real bank.
      - **Charging on the dock:** the bank has one USB-C port, so the body's USB-C power chip must turn that port round on the dock.
      - **Wireless:** using the wireless face at the same time cuts the USB-C side to 7.5 W.
      - **The phone:** whether the bank should also top it up while Pebble rests.
  - Interactive 3D sketches of the 4-, 8- and 12-motor versions were made for the owner as a claude.ai page, outside the repo.

### Learning to move
- **First, a hand-written gait engine.** A few settings cover everything above: stroke speed per side, step rate, lift height, body height, and the jump's crouch and push.
- **Pebble tunes those settings itself** (section 2) and keeps what works in its body profile.
- **Running and jumping are trained in a sim first, the owner's way** (section 2b). A physics model of the body, linkages included, is made from the CAD, in MuJoCo (Apache-2.0), on the laptop.
- **Teaching by hand:** with the drivers off but the encoders powered, the owner moves each tripod and side to its limits, and Pebble records them.

### Safety
Section 4 applies to this body. In addition:
- **Running and jumping happen only in clear space.** The usual gaps to people and animals hold, and Pebble never chases animals.
- **No jumping off a desk or down steps** unless the owner allows it. The drop sensor guards every edge.
- **"Stop" works mid-stride and mid-jump.** In the air, it lands, then stops.
- **Torque caps:** with FOC, a current limit is a torque limit, so law 1's caps live in the motor firmware.
- **Pinch points:** the push-rods, the lift links and the parallelograms need covers or gaps so fingers and paws can't be caught.
- **Test with a dummy weight first:** every new gait and every jump is tried with a 188 g dummy in the cage before the real phone.
- **Falling over:** check in the sim whether pushing the tripods and swinging the legs can roll it back up. The cage lands it on its side, never on the phone's face.

### Build order
1. Measure the Flip's USB power output, and whether it can charge wirelessly while powering its USB port.
2. CAD for the linkages: one side's swing linkage and one tripod's lift linkage, checked for reach, collisions and that swing doesn't change lift.
3. Build one lift motor and its tripod linkage. Measure torque, speed, heat, landing shocks, and finding its stops.
4. A MuJoCo model of the whole body, with checks for tipping, running, turning and jumping.
5. The whole robot with the dummy weight: walking, turning, sitting and standing, the tilt servo, the power budget.
6. Running and jumping: in the sim, then with the dummy, then with the phone.
7. Pebble tuning its own gaits.

### Tests
- Swinging a leg never changes its lift, and no leg ever passes its stops.
- Walks, runs and turns on the spot in the sim, with the scuffing on turns kept small.
- Lands feet first from every jump in the sim, and the phone cage survives drop tests at the capped height.
- Losing power at any point mid-stride or mid-jump ends on the belly.
- Finding the stops gives the same angles every time.
- The battery and USB budget is never exceeded, and the port never cuts out.
- "Stop" works mid-stride and mid-jump.
- It never jumps near a person or an animal, or off an edge it hasn't been allowed.

## 7a. The chosen body: the bare 12-motor hexapod (owner's decisions, 17–18 October 2026)
**Decided:**
- The 12-motor hexapod as designed in section 7: a swing motor and a lift motor at every hip, and parallelogram legs that keep the shins upright.
- **No shell for now.** The pebble shell (7b) is set aside.
- **The first version doesn't hop.** It is built to be fast and efficient (owner, 18 October 2026). Short hops can come in a later version; no build is tuned for high jumps.
- The motors run on the Xiaomi UltraThin Magnetic Power Bank 5000, in the belly.
- **A normal phone, not a Flip** (owner, 18 October 2026), in the same tilting head as today's wheeled body. The Flip and its 30° lean-back are set aside (see the end of this section).
- **Charging:** the Xiaomi bank stays the robot's only battery, and a connector at the dock charges everything (owner, 18 October 2026).

### The phone: today's head, on a neck (owner, 18 October 2026)
- **Why not a Flip:** Pebble runs in kiosk mode as the phone's device owner. On a Flip, its face would have to live on the cover screen, and Samsung lets only selected apps run there; nothing shows that kiosk mode works on it. A normal phone avoids the question. (A Flip with a dead inner screen is also hard to set up, because setup needs the main screen.)
- **The same head as today's wheeled body** (`interfaces.md`, "Phone mount"):
  - the phone lies sideways in its own case, screen forward, on a 26 × 50 mm case plate with a dovetail;
  - a tilt yoke, turned by an MG90S servo, holds it;
  - any phone up to 168 × 80 × 12 mm in its case fits. The phone is now a Google Pixel 6 Pro (owner, 19 October 2026): 163.9 × 75.9 × 8.9 mm bare, so about 166–168 × 78–80 × 11–12 mm in a slim case. It fits, but only just: a case more than about 2 mm thick at the ends or sides, or a rugged one, does not. Its camera bar stands out about 3 mm further than the rest of its back, so the bar goes on Pebble's right, where the yoke leaves room (`interfaces.md`, "Geometry as built");
  - the phone moves between bodies by sliding out of one head and into another.
- **On a neck:** the tilt axis sits about 118 mm above the belly, about 10 mm ahead of the middle hips.
  - Lying sideways, the phone reaches out over the hips on both sides, and its edges sweep a circle about 48 mm round the tilt axis (for the largest phone the mount takes).
  - Under it are the swing joints, whose tops sit about 62 mm above the belly, and, when resting, the folded knees, about 65 mm above the belly.
  - At 118 mm the phone clears them at every tilt: walking, resting, and when the power cuts and the body sinks.
  - The neck post stands behind the axis, with the servo lying backwards from it as on today's body.
- **Heights:** standing, the front camera is about 15–16 cm off the floor. Resting, the head's axis is at 118 mm, close to today's 132 mm.
- **The tilt servo is back.** Pebble looks ahead with the front camera, as it does today; a normal phone's wide camera is on its back. Lying sideways, the Pixel 6 Pro's front camera sees about 81° across and 65° top to bottom (Google gives 94° corner to corner; the other two are worked out for its 4:3 picture), still too little for the floor and faces at once. So the head tilts from 25° down to 90° up, resting at 8° up as today, and the legs add up to 15° either way.
- **What it sees, standing (estimates, Pixel 6 Pro front camera; worked out the same way as the first table, which was for the S22's narrower 80° camera):**

  | Head tilt | 40° down (head 25°, body 15°) | Level | 8° up, resting | 25° up | 45° up |
  | --- | --- | --- | --- | --- | --- |
  | Front camera | 73° down to 7° down | 33° down to 33° up | 25° down to 41° up | 8° down to 58° up | 12° up to 78° up |
  | Floor in view from | about 6.5 cm past the front feet | 18 cm past | 28 cm past | about 1.1 m ahead | none |
  | Standing adult's face (eyes 1.55 m up), from | not in view | 2.2 m | 1.6 m | 0.9 m | 0.3 m |
  | Seated adult's face (1.15 m), from | not in view | 1.55 m | 1.15 m | 0.6 m | 0.2 m |
  | Child's face (0.95 m), from | not in view | 1.25 m | 0.9 m | 0.5 m | 0.15 m |

  The wider camera sees the floor closer and faces nearer, but makes each face smaller in the picture: a face 40 pixels wide is about 1.5 m away instead of about 1.8 m.

- **Cameras and cable as today:** the phone's portrait top is on Pebble's right. The rear camera, on that side, looks behind for the dock's tag, and the USB-C end on Pebble's left takes a cable loop for the tilt.
- **Weight and balance:** the phone (210 g for the Pixel 6 Pro) plus its case, plate, yoke, servo and neck come to about 265 g by the same reckoning as before. That is about 45 g more than with the S22 the first figures were for, about 75 g more than the Flip and its holder, and it makes the robot about 45 g heavier than the totals further down. The head sits just ahead of the middle hips, so the power bank moves back a little.
- **Charging the phone on the dock** is the same open question as before, now for the Pixel 6 Pro: whether it charges while it is USB host to the ESP32. Test a pass-through adapter first; the Pixel 6 Pro also charges wirelessly (Qi).

### Still to check
- **The real joint sizes:** the neck height assumes swing joints about 40 mm tall and knees folding up to about 65 mm above the belly. Check in `cad/check.py` with the real joints and the largest phone the mount takes.
- **Wobble:** about 265 g on a post about 95 mm tall, at running speed.
- **The dock's tag:** the rear camera's view of it past the new neck.
- **The cable loop** over the whole tilt range.
- **The front camera's real view:** Google lists 94° corner to corner for the Pixel 6 Pro's front camera; the picture may lose a little to lens correction.
- An interactive sketch of this body, with the front camera's live view, was made for the owner as a claude.ai page, outside the repo.

### Parts research (18 October 2026)
The full research is in `reports/Hexapod motors and boards.md`, with the notes behind it in `research_notes/Hexapod motors and boards/`. Nothing in this subsection is decided yet; the owner's choices are listed at the end.
- **What it found:** at a fixed 9 V, a motor's winding resistance, not its size, decides whether it can push a hop. The hop push (0.35 Nm at 10 rad/s) is 3.5 W per lift joint. No joint of 25–30 g reaches it:
  - smart servos of that weight top out at about 2.7 W;
  - brushless joints that reach it weigh about 51–63 g, which makes the robot about 1.1–1.3 kg instead of 850–920 g.
- **Recommended set, if heavier joints are accepted:**

  | Job | Part | Size and weight |
  | --- | --- | --- |
  | Lift motors | CubeMars GL30 KV290 | Ø34.5 × 15.7 mm, 41 g, 1.53 Ω across two leads, 6 mm through-hole |
  | Swing motors | iFlight iPower GBM2804H-100T | Ø35 × 15 mm, 39 g, 10 Ω |
  | Gears | printed single-stage planetary, 8:1 | ring about 35–38 mm across, under 15 mm deep, 6–12 g |
  | Encoders | MT6701, Ø6 × 2.5 mm magnet magnetised across its face | on the joint board |
  | Joint boards | a Pebble version of SimpleFOC-microspora (STM32G431 + DRV8316, MIT) | 33 × 34 mm, on the back of each motor |
  | Motor bus | two CAN-FD buses (MCP2518FD + TJA1051T/3), one per side | about 1 kHz for 12 joints |
  | Main board | Waveshare ESP32-S3-Zero on a carrier board | 23.5 × 18 mm module; carrier about 60 × 40 mm, 4 × M2 holes |
  | IMU | ±32 g: LSM6DSO32 to prototype, ICM-45686 on the carrier | on the carrier, near the centre |
  | Edge sensors | VL53L4CD in the nose; a Pololu digital IR sensor wired only to the safety chip | 13 × 18 × 2 mm carrier |
  | 9 V from the bank | WCH CH224Q, then a TPS25947 fuse holding the bank to about 2.2 A | 2 × 2 mm chips |
  | Hop buffer | 4 × Maxwell BCAP0010 10 F supercapacitors in series | each Ø10 × 30.5 mm, 3.1 g |
  | Motor power cut | TPS25982 fuse, switched by the safety chip | 4 × 4 mm |
  | Safety chip | CH32V003 plus a TPS3430 window watchdog | on the carrier |
  | Power monitor | INA228 with a 2 mΩ shunt | on the carrier |

- **Charging at the dock:** the bank can't charge while its port powers the motors. So the dock carries plain USB-C lines from a 45–65 W multi-port charger on sprung pins to pads on the belly. While docked, a switch in the body hands the bank's port from the motors to the dock pads, and the bank and charger sort out the charge between themselves. No dual-role USB power chip is needed. The bank reaches 80 % in about 51 minutes. The motors stay off while docked, as they do when resting.
- **Charging the phone:** first test a USB-C adapter that passes charger power through while the phone stays USB host. If that fails, the fallbacks are Android Open Accessory (the body becomes the USB host and powers the phone) or a wireless coil in the holder's backrest.
- **The light alternative:** Dynamixel XL330-M288 servos on the swing joints and XC330-M181 on the lift joints (20 × 34 × 26 mm, 18–23 g, 6 V rail). This keeps the 850–920 g target but gives about 0.25 Nm at 10 rad/s, and it reverses the decision to use brushless motors with FOC.
- **Fit:** joints about 38 mm across at a 52 mm hip spacing leave only about 2–3 mm when neighbours swing towards each other, and the phone pushes the middle hips out to about ±59 mm. Check this in `cad/check.py` before ordering.
- **Licence flags:** the arduino-esp32 core is LGPL-2.1 (weak copyleft; changes to the core must stay LGPL). Waveshare's SCServo code is GPL-3.0, so keep it out. ODrive's firmware is closed.
- **How sure the numbers are:** most maker figures came from search extracts, not full pages. Build and measure one joint before buying twelve; the report lists the bench tests.
- **For the owner to decide:**
  - ~~heavier brushless joints and the full hop, or light servos and a smaller hop~~ (settled 18 October 2026: brushless joints, and no hops in the first version; see below);
  - the hip spacing;
  - how the phone charges.

### First version: fast and efficient, no hops (owner, 18 October 2026)
The owner chose to build the first version without hops, aimed at moving fast on little power. Hops can come in a later version. This changes the parts research above:
- **What the joints must do now:**
  - The lift joints' hardest moment is a fast run, not a hop: about 0.26 Nm while the foot is down and the joint barely moves, then quick, light moves while the foot is in the air.
  - The swing joints need speed: about 10–15 rad/s at the joint at top speed.
- **One motor for all 12 joints: the CubeMars GL30.**
  - It turns current into torque about three times as efficiently as the GBM2804H, at almost the same weight (41 g against 39 g).
  - It is the only candidate fast enough for the swing joints at 9 V.
- **Lower gear ratios,** each a single printed planetary stage: **6:1 on the lift joints, 4:1 on the swing joints.**
  - Lower ratios mean less friction and quieter gears, and legs that give more when bumped.
  - They also mean less of the motor's own spinning mass to swing back and forth. At 8:1, the motor's rotor would make up most of a swing joint's inertia.
- **A spring on each lift joint** carries most of the body's weight while standing.
  - Standing then costs almost nothing in the motors, and running costs about 40 % less in the lift motors.
  - Each spring carries about 80 % of its leg's share of the weight when all six feet are down. So with the power off, the body still sinks onto its belly, as section 7 requires.
- **No supercapacitors,** no precharge circuit, and no hop timing in the safety chip.
  - A few hundred microfarads on the 9 V bus smooth out each stride.
  - The 2.2 A limit on the bank stays.
- **Joint boards are switched off at rest.** They sit behind the motor power switch, so resting on the belly costs nothing.
  - Start with the 12 single-motor boards.
  - Six two-motor leg boards would save about 0.9 W while moving, and are the next efficiency step once the single boards work.
- **Legs unchanged for now:** 45 mm thighs, 60 mm shins, and a swing of about ±24°. Wider swings gain little (±30° adds about 6 % to top speed) and bring neighbouring legs closer.
- **Estimates** (a rough model, good to perhaps ±50 %; robot about 1.15–1.2 kg):

  | | Speed | Power | Time on about 14 Wh |
  | --- | --- | --- | --- |
  | Standing still | 0 | about 1.5–2.4 W, mostly electronics | 6–9 h |
  | Walking | 0.25 m/s, about 1.2 body lengths a second | about 4–5 W | about 3–3.5 h |
  | Top speed | about 0.65 m/s, about 3 body lengths a second | about 9–10 W | about 1.5 h |

  - The swing motors' 1.5 A limit sets the top speed: at 0.65 m/s the legs swing back and forth about 7–8 times a second.
  - The laws decide how fast Pebble may actually go near people and animals.
- **Cost:** 14 GL30 motors (12 and 2 spares) cost about US$710–1,110 at the prices seen, before gears, springs and boards. The official store is sold out, so find a source first.
- **Cheaper option:** GBM2804H motors on the lift joints (8:1 plus spring) save about US$200–400. They use about 20–25 % more power and top out at about 0.5 m/s.
- **Weight is still the weak point:** twelve 41 g motors put the robot at about 1.15–1.2 kg. A lighter low-resistance motor for the swing joints would help: bench-test the 26 g 2204 260KV and look for a smaller GL-series motor.
- **First bench tests:**
  - one lift joint (GL30, 6:1, spring) and one swing joint (GL30, 4:1): torque, heat, noise and power through walking and running motions;
  - the joint boards' idle power.

### Set aside for now: a Flip leaned back 30° (17–18 October 2026)
Kept in case a Flip comes back, for example if kiosk mode turns out to work on its cover screen.

**What was worked out:**
- **Hinge down.** On a folded Flip, the cameras are at the same end as the USB-C port, away from the hinge. Standing hinge down puts them at the top: about 11 cm off the floor when standing, about 7.5 cm when resting. Samsung's own cover-screen layout may then be upside down; Pebble draws its own face, so it turns it the right way up. This replaces section 7's hinge-up layout, which would put the cameras down by the deck.
- **The plug goes in at the top:** a right-angle USB-C plug pointing back, with its cable running down the back of the holder to the main board.
- **The holder is printed at 30° back.** There is no tilt servo; the legs lean the whole body up to 15° either way when it needs more.
- **The front of the deck slopes down,** from 22 mm high at 50 mm forward to 7 mm at the nose, so it stays out of the bottom of the wide camera's view.
- **The picture is taller than it is wide** when the folded phone stands up. The wide camera covers about 106° top to bottom and 90° across (13 mm equivalent, full 4:3 picture). The main camera covers about 74° by 59° (23 mm equivalent).
- **Why 30°:** at about 37°, the top edge of the wide view points straight up. Past that, the top of the picture only looks back over Pebble's own head, while the floor in front keeps shrinking. 30° keeps a margin.
- **What it sees, standing level (estimates):**

  | Leaned back | Straight up | 15° | **30°, chosen** | 35° |
  | --- | --- | --- | --- | --- |
  | Wide camera | 53° down to 53° up | 38° down to 68° up | 23° down to 83° up | 18° down to 88° up |
  | Floor in view, past the front feet | 2 cm | 5 cm | 14 cm | 21 cm |
  | Standing adult's face (eyes 1.55 m up), from | 1.1 m | 0.6 m | 0.2 m | any distance |
  | Seated adult's face (1.15 m), from | 0.8 m | 0.4 m | 0.15 m | any distance |
  | Child's face (0.95 m), from | 0.65 m | 0.35 m | 0.1 m | any distance |
  | Main camera | 37° down to 37° up | 22° down to 52° up | 7° down to 67° up | 2° down to 72° up |
  | Standing adult's face in the main camera, from | 1.95 m | 1.15 m | 0.6 m | 0.5 m |

- **The floor right in front:** leaning the body 15° forward brings the floor into view from about 5 cm past the front feet, for creeping and before a step. The drop sensor still guards every edge.
- **Which camera for what:** the wide camera for everyday watching, with the floor and faces in one picture; the main camera for detail, such as faces across the room.
- **Balance:** leaning the phone back moves its weight about 2 cm back, and the robot's centre of mass about 5 mm. The power bank moves about 5 mm forward to make up for it.
- **The face leans back too,** which suits people looking down at it.

**What was still to check:**
- **On a real Flip 7:** where the two lenses sit and which is which. The sketch puts the wide lens 12 mm below the top edge and the main lens 28 mm below.
- **Use the full 4:3 picture.** A 16:9 picture crops the sides to about 78° across.
- **That the app can open the wide camera.** On recent Samsung phones, asking the main rear camera for 0.6× zoom switches to it. Check this through CameraX on the Flip.
- **The real view angles** with Samsung's lens correction on. Samsung quotes 123° corner to corner for the wide camera; the numbers above use a slightly narrower view to be safe.
- **Stretched edges:** things near the top and bottom of the wide picture look stretched, so the brain undoes the lens shape before it looks for faces.
- **Ceiling lights** in the top of the picture can make faces too dark. Set the exposure from the lower part of the picture and from faces.
- **Its own legs:** the front knees can show in the bottom corners when the body leans forward. The brain knows the leg angles and ignores them.

## 7b. Set aside for now: the pebble shell (owner, 17 October 2026)
The owner asked for a pebble-shaped shell round the 12-motor hexapod, then set it aside for the bare body (7a). The work is kept here in case it comes back.

**What was decided before it was set aside:**
- The 12-motor hexapod as designed in section 7: a swing motor and a lift motor at every hip, and parallelogram legs that keep the shins upright.
- Normal running and short hops. The gimbal-class lift motors stay; no build tuned for high jumps for now.
- The motors run on the Xiaomi UltraThin Magnetic Power Bank 5000, in the belly.
- **A pebble-shaped shell built round it,** so that if it falls over it rolls back onto its belly.
- **When it sits, the legs fold in** and become part of the shell.
- **The front stays open** while the phone is up, so the cameras see clearly.
- **A small actuator lays the phone down to hide it,** and the whole body then looks like a pebble.
- **Set aside:** curved "petal" legs that formed the shell themselves. The owner wanted the hexapod's own legs kept.

### The shell
- **Shape:** a rounded loaf, 200 × 142 × 109 mm.
  - Seen from the front, every slice is a circle of radius 71 mm, cut flat 33 mm below the centre to make the belly.
  - It rolls about its long axis, 38 mm above the floor.
  - The middle 70 mm is straight, and the ends round off over 65 mm.
- **Why it rights itself:** the heavy parts are low: the power bank in the belly, the motors at the hips, and the phone lying flat on the motors. With the legs folded and the phone hidden, the centre of mass is about 29 mm up, 9 mm below the roll axis.
- **Checked by calculation, from estimated part weights (about 830 g):** 240 random starting orientations were each left to slide downhill on the shell's potential, and all 240 ended belly down.
- **The ends had to be made rounder.** With flatter ends (only 26 mm of rounding), the same check found it could balance on its nose or its tail.
- **With the phone up and the doors open,** it could prop itself on them. So when Pebble feels a fall, it:
  - folds its legs;
  - lays the phone down;
  - closes the doors.

### Legs folding in
- **To sit:**
  1. Each leg lifts its thigh to its 80° stop.
  2. It swings round to lie along the body: the front and middle legs point back, the back legs point forward.
  3. The belly comes down onto the floor.
- **Order matters.** Legs swing out before they lower, and lift before they swing in, so neighbours never meet. The firmware enforces it.
- **Each shin carries a curved cover.** Tucked, the six covers close a band round the lower sides of the shell, from 8 mm to 60 mm above the floor. That band is where walking legs pass, so it can't be fixed shell.
  - Front covers span x 22 to 80 mm, middle covers −19 to 19 mm, back covers −80 to −22 mm.
  - Walking, the covers ride on the shins like shin guards. They stop about 9 mm above the feet, so they never scrape.
- **The upper sides,** above the band, are fixed shell.

### The phone and the doors
- **The phone holder** stands on the deck, with the tilt pivot 30 mm behind the middle and 34 mm above the belly. A small servo tilts it from 20° back to 90° forward.
- **Upright:** the phone stands between the open doors, with nothing in front of the cameras.
- **Tilted part-way:** it looks down at the floor.
- **Hidden:** it lies flat on the motors, screen down, 34 to 48 mm above the belly. Keeping it this low is what keeps the centre of mass under the roll axis.
- **Two doors in the top close over it,** like a beetle's wing cases. They are hinged along the sides of the opening, 40 mm either side of the middle and 95 mm up, and swing up and out to open.
  - Springs close them, and the rising phone pushes them open; a second small servo could drive them instead.
  - The opening runs from x −46 to 58 mm.

### Behaviour
- **Falling:** a reflex tucks the legs, lays the phone down and shuts the doors. Pebble rolls back, says something like "Whoa! I'm okay.", then opens up and stands again.
- **Resting** is the pebble pose: belly down, legs tucked, phone hidden, every motor off.
- **The phone gets warm** face down under the doors, so Pebble thinks lightly while hidden (agency plan, section 3b).

### Still to place or check
- **The front lift motors** come within a few millimetres of the shell. Widen the shell slightly or use slimmer motors if needed, then re-run the righting check.
- **The knee blocks** come close to the upper shell while the legs swing out. Check the clearance in CAD.
- **Soft lips** on the gaps round the covers and doors, so fingers, paws and dust can't get in.
- **Still to place in the new shell:**
  - the charging contacts on the belly;
  - the drop sensor in the nose;
  - the room-air sensor's vent;
  - the bumper;
  - the phone's USB cable through the tilt pivot.
- **CAD** (`cad/`):
  - model the shell, covers, doors and phone holder;
  - weigh the real parts;
  - add the righting sweep to `cad/check.py`.

  The sweep finds the centre-of-mass height for each orientation (the furthest point of the shell in that direction, minus the centre of mass in that direction). It lets many random starts slide downhill, and checks that they all end belly down.
- **Drop-test** the closed shell before trusting the phone in it.
- Interactive 3D sketches of this body (folding, hiding, walking and rolling back after a fall) were made for the owner as a claude.ai page, outside the repo.

## 8. A humanoid body: Poppy on cheaper servos (owner's idea, 23 October 2026)
The owner's question: could Pebble live in a full humanoid like INRIA's Poppy Humanoid, made much cheaper than the original, keeping Poppy's design and parts, with the phone as the main brain, a Raspberry Pi to drive the servos, and batteries to move it?

**Decided (owner, 23 October 2026):**
- Poppy Humanoid's design and printed parts: about 84 cm tall, 3.5 kg, 25 joints, with its 5-joint spine. Printed at home.
- The phone is the brain, face and cameras, as in every body.
- A Raspberry Pi drives the servos.
- 3S LiPo packs of about 3,000 mAh, kept close to the centre of mass: in the pelvis and the lower belly, not in the limbs.

**Looked at and set aside (23 October 2026):**

| Robot | Cost to build | Why not |
| --- | --- | --- |
| PhoneBot (UCLA) | about US$400 without the phone | Legs only, no arms; the owner wants a full humanoid like Poppy |
| Aster (a Poppy remix) | under US$200 | MG996R hobby servos; it can't walk |
| Zeroth Bot (K-Scale) | about US$350 | 40–46 cm, no hands, and K-Scale has moved on from it |
| Microban (Rhoban) | about US$567 | 30 cm, too small to carry a phone well on its XL330 servos |
| HOPEJr (Hugging Face) | about US$3,000 estimated | Dexterous hands, but full-size and still mostly remote-controlled |
| ToddlerBot (Stanford) | under US$6,000 | Has grippers, but most of the cost is Dynamixels and a Jetson |
| Berkeley Humanoid Lite | under US$5,000 | Printed brushless joints; costly |

### Where the money goes in the original
- A complete Poppy costs US$8,000–9,000, about 60 % of it on 25 Dynamixel servos:
  - 19 MX-28AT, about €245 each;
  - 4 MX-64AT, about €350 each: both hips' forward swing (`hip_y`) and the abdomen's forward and sideways bend (`abs_y`, `abs_x`), per Poppy's configuration file;
  - 2 AX-12A in the head, about €45 each.
- The original paper put the actuators at €4,700 of €7,500, and €1,200 for professional 3D printing in polyamide.

### The servos: Feetech serial-bus servos in place of the Dynamixels

| Original | Replacement | Torque (stall, at 12 V) | Size | Weight | Price seen |
| --- | --- | --- | --- | --- | --- |
| 19 × MX-28AT (2.5 Nm, 35.6 × 50.6 × 35.5 mm, 77 g) | Feetech STS3215-C018 | 30 kg·cm (about 2.9 Nm), rated 10 kg·cm | 45.2 × 24.7 × 35 mm | 55 g | about US$26–29 |
| 4 × MX-64AT (126 g): hip swing and abdomen | Feetech STS3250 | 50 kg·cm (about 4.9 Nm), rated 16 kg·cm, a little under the MX-64 | the same body as the STS3215 | 74.5 g | about €76–US$125 |
| 2 × AX-12A, head | Feetech STS3215-C018 | as above | as above | 55 g | about US$26–29 |

- All 25 come to about US$900, against about €4,700.
- One bus and one voltage: all of them run on 12 V, like the originals.
- They report position, load, current, voltage and temperature, and cut out on overload and overheating. That makes teaching by hand (section 2b) precise.
- The hexapod research found reports of STS3215 gears stripping after stalls (`research_notes/Hexapod motors and boards/smart_servos_alternatives.md`). Keep torque limits set in every servo, and buy spares.

### Buying the servos: AliExpress prices (23 October 2026)
The same Feetech servos cost much less on AliExpress. Prices are New Zealand dollars without GST (15 % is added at checkout), read from each listing's 12 V servo option. US$1 was NZ$1.76 that day.
- **Open the listing before trusting a price.** The prices on AliExpress search pages are mostly for brackets, driver boards or the weaker 7.4 V version.

| Servo | Listing | Price | Each |
| --- | --- | --- | --- |
| STS3215 12 V 30 kg | [stemedu Official Store, 6-pack](https://www.aliexpress.com/item/1005009214017320.html) (110 sold) | NZ$191.79 | NZ$32 |
| STS3215 12 V 30 kg | [Waveshare ST3215, single](https://www.aliexpress.com/item/1005009743256558.html): made by Feetech under Waveshare's name, same bus protocol | NZ$34.89 | NZ$34.89 |
| STS3215 12 V 30 kg | [stemedu Official Store, single](https://www.aliexpress.com/item/1005008856944075.html) (477 sold) | NZ$37.89 | NZ$37.89 |
| STS3250 12 V 50 kg | [2-pack](https://www.aliexpress.com/item/1005010806397582.html) (168 sold, 4.6 stars) | NZ$184.19 | NZ$92 |
| STS3250 12 V 50 kg | [RCmall Store](https://www.aliexpress.com/item/1005012463197951.html) or [stemedu Official Store](https://www.aliexpress.com/item/1005009439334793.html), single | NZ$108.79–111.99 | NZ$109–112 |

- **All 25:** three 6-packs, three Waveshare singles and two STS3250 2-packs come to NZ$1,048 without GST: about NZ$1,205 with it, or about US$595. The table above puts them at about US$900 (about NZ$1,580).
- **Spares:** a fourth 6-pack in place of the three singles gives 3 spare STS3215s, for NZ$1,136 in all.
- **Cheaper, but unproven:**
  - a [Gintech ST3215 12 V at NZ$23.29](https://www.aliexpress.com/item/1005010341100355.html), from a store with 4 sales;
  - a [vvhobby STS3215 at NZ$30.39](https://www.aliexpress.com/item/1005008486898657.html), whose title says 12 V 30 kg but whose description gives 6 V figures. Ask the seller to confirm it's the C018 first.
- **Looked at, and not cheaper:**
  - the all-metal STS3235, 30 kg, NZ$78.99: a tougher choice if gears strip;
  - the HLS3950M, 50 kg, NZ$121.19, in a different case;
  - Hiwonder's HTS-35H, NZ$37–41, on another protocol, so it needs a second bus;
  - the 7.4 V STS3215: 19.5 kg·cm, too weak.
- **Stronger hips and abdomen, if the STS3250 isn't enough:**
  - Waveshare's RSBL85-12, 85 kg·cm and brushless, about NZ$330 each;
  - a Steadywin GIM6010-8 with its driver, NZ$145 (see "Later: brushless joints" below);
  - against the MX-64AT at about €350 (about NZ$690).

### Keeping Poppy's shape
- The Feetech body fits inside the MX-28's outline, but the screw holes, horn and spline differ. Poppy's forum confirms that different servos don't drop into the stock parts.
- So every servo pocket and horn mount is redrawn, while the outer shapes and the joint positions stay as Poppy's. Mostly that means filling the pockets in to hold the smaller servo.
- Redraw the parts as Python in `cad/`, like today's body, so `cad/check.py` can check collisions and joint ranges.
- Print the legs and hips in PETG or a nylon-carbon filament with thick walls, not PLA; the original was printed in polyamide.
- **Licences:** Poppy's hardware is CC BY-SA and its software GPL-3.0. The redrawn parts stay CC BY-SA; list them in NOTES.md ("Licences of the parts") once they're in the repo. For the servo code, LeRobot (Apache-2.0) has a Feetech driver in Python. Keep Waveshare's SCServo code out, as section 7a says.

### The phone, the Pi and the link
- **The phone goes in the head,** in place of Poppy's screen and camera, its screen the face. The two head servos pan and tilt it, so no tilt yoke is needed.
  - Check that the head takes a Pixel 6 Pro lying sideways (about 166–168 × 78–80 mm in a slim case, `interfaces.md`). If not, widen the face plate and keep the outline.
  - The phone (210 g plus its case) sits high up. Check the neck servos and balance with the real head.
- **The Pi moves from Poppy's head to the torso or pelvis,** near the batteries.
- **The link:** the phone talks to the Pi over USB, with the Pi in USB gadget mode so the phone stays host as it is with the ESP32 today (to check). Wi-Fi is the fallback. The Pi speaks the same link protocol as the wheeled body (`interfaces.md`), with a humanoid body profile (section 3).
- **The servo bus:** the Pi drives the Feetech bus through a small bus adapter board.
- **Reflexes and safety:** the reflexes (stop, sit, fall) run on the Pi, so they never wait on the phone. The Pi isn't a real-time board, so section 4's safety chip cuts servo power on "stop", a fall or a lost heartbeat, and the servos' own limits are the last backstop.

### Power: 3S LiPos near the centre of mass
- A 3S LiPo (11.1 V nominal, 12.6 V full) feeds the 12 V servos directly. A 5 V regulator powers the Pi.
- **The weight budget:** the servo swap saves about 620 g (19 × 22 g, plus 4 × about 51 g). A 3S 3,000 mAh pack weighs about 230–260 g.
  - **Two packs, about 500 g:** no heavier than the original 3.5 kg.
  - **Three packs, about 750 g:** about 150 g over the original. Treat three as the limit.
  - The phone against Poppy's original head electronics isn't counted yet; weigh both.
- **Where:**
  - the pelvis, between the hip servos, first: low and central, and still when the spine bends;
  - the lower belly, just above it, second;
  - never the chest, where the 5-joint spine swings the weight about, and never the shins, feet or forearms, where weight costs the servos most.
- **Wiring:** the packs in parallel, identical, at the same charge, each with its own fuse, and balance-charged separately.
- **Falls:** humanoids fall a lot, and a crushed LiPo can catch fire. Each pack sits in a rigid printed pocket, away from the joints' pinch points.
- **Current:** an STS3215 can draw 2.7 A stalled, and the STS3250s more, so 25 servos straining together can pull tens of amps. Three packs in parallel cover it easily.
- **Option:** 3S packs of high-drain 18650 cells. Their steel cans survive falls far better than pouches.
- **Runtime (estimate, to measure):** at an average of 3–6 A while moving, each 3,000 mAh pack gives about 30–45 minutes. Three give about 1.5–2 hours, more when it stands still.
- **Charging the phone:** the same open question as the hexapod (section 7a).

### Cost (estimate)
About US$1,100–1,300 in all: about US$900 of servos, plus the Pi and bus adapter, the packs and a balance charger, filament, bearings and screws. The original is US$8,000–9,000.

With the servos from AliExpress (about US$595, see "Buying the servos"), the whole robot comes to about US$800–1,000.

### Hands
Poppy's hands don't grip. A small gripper on an STS3215 at each wrist would add the fetching and carrying that `everyday-uses.md` lists as missing. Not designed yet.

### Later: brushless joints where the torque is
- Brushless motors with encoders and FOC, in printed gearboxes, cost about US$65–74 a joint built at home, against about US$200 for each original Dynamixel.
- They give torque control and joints that give when pushed, which is better for walking, falling and learning.
- The catch: bigger joints, a redesign of the parts around them, and 12–16 control loops to tune.
- **The sensible mix if it comes:** brushless joints in the hips, knees, ankles and perhaps the shoulders; Feetech servos for the head, wrists and grippers.

### What brushless joints would cost (AliExpress, 23 October 2026)
Brushless joints don't make the robot cheaper. A Feetech servo brings the motor, gearbox, encoder, driver and case for NZ$32; built from parts, a joint costs nearly twice that. Having Claude write the joint code doesn't change this: the motor control already exists as the open SimpleFOC library, and the cost is in the parts, the bulkier joints and the tuning on the bench.

Prices are New Zealand dollars without GST, as in "Buying the servos".

| Part of one home-built joint | Listing | Price |
| --- | --- | --- |
| 5010 360KV drone motor | [single](https://www.aliexpress.com/item/1005005438724862.html) (362 sold) | NZ$20.09 |
| MT6701 magnetic encoder | a module, from several sellers | about NZ$4–5 |
| Half of a two-motor FOC board with current sensing | [MKS ESP32 FOC Mega](https://www.aliexpress.com/item/1005011652368824.html), NZ$29.89 for two motors; boards for higher currents cost up to about NZ$57 | NZ$15–30 |
| Two thin bearings, a printed 10:1 planetary gearbox, magnet, screws, wires | 6806 bearings about NZ$1 each in tens | about NZ$10 |
| **One joint** | | **about NZ$50–65** |

- This is less than the US$65–74 a joint above, which assumed better motors. A drone motor like this needs a driver that can give 5–15 A.
- **Ready-made brushless joints** (motor, gearbox, encoder and driver in one):

  | Module | Listing | Price |
  | --- | --- | --- |
  | Steadywin GIM6010-8 with a GDS68 driver, sold as 5 Nm | [listing](https://www.aliexpress.com/item/1005013199573112.html) (367 sold) | NZ$145.39 |
  | Steadywin GIM4310-10 with a GDZ34 or GDS34 driver | [listing](https://www.aliexpress.com/item/1005013054939951.html) (376 sold) | NZ$186–232 |
  | Damiao DM-J4310-2EC | several listings | NZ$230 and up |

- **The whole robot's servos:**

  | Choice | Cost (NZ$, without GST) |
  | --- | --- |
  | All Feetech ("Buying the servos") | about 1,050 |
  | Home-built brushless in the 4 strong joints only (hip swing and abdomen), Feetech elsewhere | about 880–940, with stronger joints there |
  | Home-built brushless in the 10–12 leg joints, Feetech elsewhere | about 1,000–1,200 |
  | All 25 home-built brushless | about 1,250–1,630 |

- **Costs the code doesn't remove:**
  - **Size:** a 5010 with its gearbox is about 60 mm across, against 45 × 25 × 35 mm for an STS3215. Poppy's limbs would be redrawn round it, not just their servo pockets.
  - **Weight:** roughly 130–150 g a joint against 55 g (an estimate; weigh one). Over 25 joints that is about 2 kg more, and heavier legs need stronger joints.
  - **Holding still:** a joint that gives when pushed draws current to hold a pose, while the STS3215's 345:1 gears hold it almost for free. Standing then costs battery, unless springs carry the weight as in the hexapod (section 7a).
  - **Current:** 5–15 A a joint in a hard move at 12 V. Size the drivers, wiring and fuses for it.
  - **Spares:** expect to replace a few boards and reprint a few gearboxes.
- **What brushless buys is better legs, not a lower price:** joints that feel force and give when pushed. That is the sensible mix above.

### Options looked at: cables and other actuators (23 October 2026, not designed yet)
Two options passed a check of whether this repo's tools can design them and whether every part they need is counted. Nothing is drawn yet; the design waits for the owner.

**Can it be designed here?** Yes, within these limits:
- **CAD:** the same Python and manifold3d tools as the tank body, with `cad/check.py` for collisions and joint ranges.
  - Poppy's parts exist only as 52 STL meshes and a SolidWorks assembly without its part files. Every changed part is redrawn as Python, with the STL as the reference.
  - Cables change more parts than the plain servo swap: the pelvis, thighs, shins and torso.
- **Simulation:** MuJoCo loads Poppy's URDF (joint positions, limits and masses) and models cables as tendons over pulleys. It isn't in the repo yet (`pip install mujoco`, Apache-2.0).
- **Electronics and firmware:** ESP32 limb boards like the tank body's, and LeRobot's Feetech driver on the Pi. The maths is standard: undoing the pull the knee puts on the ankle cable, mixing the hip differential, the two-rod ankle, and the twisted-string model.
- **Only the bench can settle:**
  - how much Vectran stretches and drags over printed pulleys;
  - push-rod speed and force with the chosen motor and screw lead;
  - how long the hand strings last;
  - the real masses.

**Option A: the cable layout (23 servos, all STS3215, none of the strong ones)**

| Part | Poppy | With cables | Motors |
| --- | --- | --- | --- |
| Head | 2 | Unchanged: direct pan and tilt for the phone | 2 |
| Arms | 8 | Unchanged: cables across a 3-axis shoulder get messy | 8 |
| Spine | 5 (2 strong) | One pair of cables bends both sections forward and back together, a second pair bends them sideways, twist stays direct. Motors low in the pelvis; the cables pull about 3 times further from the bend than the servo's drum is wide, roughly 7–8 Nm after friction (estimate) | 3 |
| Hips | 6 (2 strong) | Forward swing and sideways lift share two servos through a cable differential in the pelvis: either axis gets both servos' strength, up to about 5.8 Nm, when the other is lightly loaded. Turn stays direct | 6 |
| Knees | 2 | Servo at the top of the thigh, cable to a drum at the knee | 2 |
| Ankles | 2 | Servo on the thigh, cable over a pulley on the knee axis to the ankle; software undoes the knee's pull | 2 |

- Each shin and foot loses about 110 g of servo.
- Vectran, not Dyneema: it barely stretches under a load that never lets up. Steel wire rope would need pulleys 20–30 times its thickness.
- An angle sensor on every cable joint reads the joint itself, not the servo, so stretch doesn't become error.

**Option B: push rods and twisted strings, on top of A**
- **Knees:** a geared motor turns a T8 lead screw that pushes a rod.
  - A 2 mm lead holds the robot up with the power off, but is slow: roughly 50–60°/s at the knee (estimate).
  - An 8 mm lead is four times faster, but doesn't hold itself.
- **Ankles:** two push rods side by side tip each foot forward and back and side to side. That adds the sideways balance Poppy's ankles lack, for one more motor per leg.
- **Hands:** a small motor twists two strings together to close three fingers; springs open them. The strings wear, and are replaced like a part.
- The four knee and ankle servos come out: 19 servos, 6 push rods and 2 hand motors.

**Every part they need** (NZ$ without GST; AliExpress search-page prices on 23 October 2026, so open the listing first; counts are before design)

| Part | Option | Count | About (NZ$) |
| --- | --- | --- | --- |
| STS3215 12 V, four 6-packs ("Buying the servos") | A: 23 + 1 spare; B: 19 + 5 spares | 24 | 767 |
| Vectran line, about 1 mm | A, B | 50–100 m | 15–30 |
| Crimp sleeves or spliced ends, and a crimp tool | A, B | about 40 | 15 |
| Cable tensioners: printed, on M3 screws | A, B | about 16 | in filament and screws |
| Idler pulley bearings (MR105, 623 or 625) | A, B | 30–40 | 30–40 |
| Thin bearings for the drums and the hip differential (6800–6805) | A, B | 8–12 | 10–15 |
| Steel pins or bolts for pulley axles | A, B | about 30 | 5–10 |
| MT6701 angle sensors with 6 × 2.5 mm magnets | A: 10; B: 16 | 10–16 | 45–80 |
| Sensor reader: a small board on the Pi, or the limb boards, plus an I2C splitter (every MT6701 has the same I2C address) | A, B | 1–2 | 10–20 |
| Springs: cable pre-tension, hand opening | A, B | about 10 | 5–10 |
| Extra filament for drums, pulleys and rod mounts | A, B | about 0.5 kg | 15–25 |
| JGA25-370 12 V geared motor with encoder; speed picked on the bench | B | 6 + 1 spare | 55–135 |
| T8 lead screw and anti-backlash nut | B | 6 + 1 spare | 40–65 |
| Shaft couplers and thrust bearings | B | 6 sets | 15–25 |
| Rod-end ball joints (M4 or M5) | B | 12 | 15–35 |
| Ankle cross joints: printed, 4 bearings each | B | 2 | 5–10 |
| Hand motors: N20 with encoder | B | 2 | about 28 |
| Motor drivers: DRV8871 for the push rods, DRV8833 for the hands | B | 6 + 1 | 15–25 |
| Limb boards: an ESP32-S3 counts only 4 motor encoders in hardware, so two boards, or steer by the joint sensors alone | B | 2 | 20–30 |

- **Option A:** about NZ$920–980, against about NZ$1,080 for plain servos with one spare.
- **Option B:** about NZ$220–380 more than A, so more than plain servos. Buying 20 servos instead of 24 takes about NZ$120 off.
- **Every version, cables or not:** the actuator power cut for section 4's safety chip, rated 30–40 A, with a fuse per branch (about NZ$30–50). It isn't in "Cost (estimate)" yet.
- **Unchanged:** the Pi, the bus adapter, the packs and charger, the regulator, and the screws already counted in "Cost (estimate)".
- **Tools, if not already owned:** a bench power supply with a current limit, for first runs of the motors, and a luggage scale to set cable tension.

**Looked at and set aside:**
- **One motor for several joints through a switching gearbox:**
  - a clutch and brake per joint costs about NZ$90 a joint (micro clutch NZ$52, holding brake from NZ$37), more than a servo;
  - a selector gearbox saves only NZ$15–20 a joint, moves one joint at a time, wastes about half the torque in its worm gears, can't be moved by hand and strips in a fall;
  - a one-way-bearing box pushes each joint one way only.
  - Fixed couplings, like option A's spine and the hands, are the kind worth having.
- **Air muscles:** the compressor is noisy beside Pebble's hearing, each muscle needs two valves (NZ$10–18 each), and air is poor on battery.
- **Memory wire and coiled nylon:** seconds to cool, about 1–2 % efficient.
- **Cheaper motors driving joints directly** (MG996R, DS3218, N20, JGB37-520): no position feedback, too weak, or dearer once a driver and sensor are added.

### Trade-offs
- Feetech servos' own control is cruder than the Dynamixels', so expect more tuning for the same smoothness.
- Walking an 84 cm biped is hard; Poppy was built for walking research. Pebble learns its gait in a sim first (section 2b, MuJoCo), then on a harness.

### Safety
Section 4 applies to this body. In addition:
- **A falling 4 kg robot can hurt a child or a pet.** Walking is learned on a stand or harness, only in clear space, and never with a person or animal near.
- **Torque limits** are set in every servo, and learning never raises them.
- **Falls protect the phone:** a planned way of falling that keeps the phone's face off the floor. To design in the sim.
- **Pinch points** at the knees, elbows, hips and spine need gaps or covers.

### For the owner to decide
- two or three packs;
- STS3250s in the hip swing and abdomen joints, or keep MX-64s there (stronger, dearer), or a Steadywin GIM6010-8 (stronger, NZ$145 each; see "What brushless joints would cost");
- the cable layout (option A) and the push rods and twisted strings (option B) in "Options looked at", or plain servos;
- grippers now or later;
- which Pi.

### Build order
1. Get Poppy's parts files, redraw one leg's servo pockets for the STS3215 and STS3250 in `cad/`, and print it.
2. Bench-test that leg on the Pi: torque, heat, current, and holding a pose.
3. The phone in the head, and the link to the Pi.
4. The whole robot on a stand: standing, sitting, arm and head moves, the power budget, and weighing it.
5. A MuJoCo model, and walking in the sim.
6. Walking on a harness, then free.
7. Pebble tuning its own gaits (section 2).

### Tests
- No redrawn part moves any of Poppy's joint positions.
- "Stop" works mid-step.
- Every fall in the sim keeps the phone's face off the floor.
- The packs' current limit is never exceeded.
- Learning never raises a servo's torque limit.
- It never walks near a person or an animal.

### Where the numbers came from (23 October 2026)
- [Poppy Humanoid repository and cost](https://github.com/poppy-project/poppy-humanoid)
- [Poppy servo counts and prices (Polytech)](https://forge.polytech.uca.fr/attachments/download/14493/Poppy_robot.pdf)
- [The original Poppy paper (IROS 2013)](http://vigir.missouri.edu/~gdesouza/Research/Conference_CDs/IEEE_IROS_2013/media/files/0591.pdf)
- [Poppy forum: different servos don't fit the stock parts](https://poppy.discourse.group/t/some-questions-on-the-poppy-humanoid/4817)
- [Dynamixel MX-28AT](https://robotis.us/dynamixel-mx-28at)
- [Feetech STS3215](https://aifitlab.com/products/feetech-sts3215-servo-motor) and [STS3250](https://aifitlab.com/products/feetech-sts3250-servo-motor), and [prices at OpenELAB](https://openelab.io/it/collections/feetech-motor)
- [A printed brushless actuator (Hackaday.io)](https://hackaday.io/project/177599-3d-printed-robotic-actuator) and [TipTap's](https://hackaday.io/project/163093-tiptap/discussion-140318)
- AliExpress prices: the listings are linked in "Buying the servos" and "What brushless joints would cost". The exchange rate is from [Frankfurter](https://api.frankfurter.dev/v1/latest?from=USD&symbols=NZD,EUR) (22 October 2026 rates).
