# Useful every day, beyond programming boards (plan, not built)

The owner's question, 17 October 2026: Pebble will be able to program Raspberry Pis and ESP32s (`workbench.md`), so how else can it be useful? The ideas below were put to the owner, who asked for all of them to go into a plan.

What sets Pebble apart from a smart speaker is the mix: it moves, it sees, it knows the people in the house, and it can build its own sensors, all offline. Each idea here uses at least two of those.

## Rules for all of it
- **Offline.** Nothing leaves the house except the existing notices to the owner's phone, which are opt-in and words only.
- **Ongoing uses are responsibilities** (agency plan, section 3c). Pebble chooses them, the laws' ladder orders them, and it says plainly when it missed one.
- **Limbs that could hurt** (heaters, locks, pumps, mains switches, garage doors) need the owner's approval per device. Every action goes through the gatekeeper and law 1.
- **Health reminders are only reminders.** Pebble never gives medical advice.
- **It is not** a medical alert, a smoke or CO alarm, or a security system. It watches and tells people; it never scares anyone off.
- **Photos of people** get "Should I keep these?", as for the Wi-Fi inbox.

## 1. Using what already exists
These are mostly joining up parts that are built or already planned.

### 1a. Messages, reminders and timers that come and find you
- **What people say:**
  - "Tell Sam dinner's ready."
  - "Remind Ina at 6 to call the plumber."
  - "When Mo gets home, say the parcel's in the garage."
  - "Rubbish goes out every Tuesday night, remind us."
  - "Set a timer for the rice, 15 minutes."
- **What Pebble does:**
  - It finds the person by face and voice, drives there, and says it.
  - It waits for a sign the message got through: an answer, or the person looking at it. It tries once more if there is none.
  - If it can't find them, it tells the sender. A message it couldn't deliver is never silently dropped.
  - Timers can run side by side, each with a name ("the rice"). When one is up, Pebble comes to whoever set it.
  - Repeating reminders cover things like bins night and "every weekday at 8".
- **Privacy:** a message is said only to the person it's for, when they are alone, unless the sender says "say it out loud". This works like overheard facts today.
- **Built on:**
  - the request rules, which gain "tell", "remind" and "timer" as their own kinds (today "remind" and "tell" are only verbs that mean "not a motion request");
  - goals and tasks (`goals.py`) and people memory;
  - navigation and finding people;
  - the promises book (agency plan, 3c). A reminder Pebble agreed to is a promise.
- **Limit:** at 0.25–0.3 m/s, crossing a house takes a minute or more. Urgent news should go by phone.

### 1b. Maps of the house
- **What it records while driving its rounds,** each reading with its place on the nav grid and the time:
  - light, temperature, humidity and air pressure, which already stream to the brain;
  - Wi-Fi strength, which is new: the phone can read the signal of the network it is on.
- **What it tells people:**
  - **Damp:** rooms that sit above about 70 % humidity for long stretches. "The back bedroom stays damp overnight. Airing it in the morning would help." Mould is common in NZ houses.
  - **Cold:** which rooms are coldest, and when.
  - **Light:** where the sun falls and for how long, so it can say which plant would do better where.
  - **Wi-Fi:** where the signal is weak. This feeds the workbench: before a gadget goes somewhere, Pebble can say whether Wi-Fi reaches it.
- **Seeing it:** coloured layers on the `/map` view (`nav/mapview.py`), and plain answers to "Where's the dampest room?" or "Will Wi-Fi reach the garage?"
- **Stored in** the time-series store (workbench, section 10), thinned with age like device readings (storage plan).
- **Limits:**
  - the air sensor sits a few centimetres above the floor, so it reads colder than head height;
  - the phone's light sensor faces wherever the face points, so light is rough;
  - the maps need a few weeks of rounds before they say anything.

### 1c. Desk buddy
- A focus timer with lengths the person picks.
- "You've been sitting for 90 minutes. Time for a stretch?" It uses the posture reading ("sitting") and knowing who is there.
- Nudges to drink water.
- Only for people who ask for it, and "not now" quiets it. Nudges someone asked for don't count towards the limit on speaking up unasked.

### 1d. Finding dropped parts
- "I dropped a screw" → Pebble sweeps the floor near the person or the bench, slowly, with the camera tilted down.
- It uses the floor scan and "find a thing", and treats the search area with care so it doesn't drive over the part.
- It says where it thinks the part is ("by the chair leg, near my left wheel") and shows a picture on its face.
- **Limit:** something a few millimetres wide is only seen close up. Measure how close on the Pixel 6 Pro.

### 1e. A round before bed, and a morning report
- When the last person goes to bed (or at a set time), Pebble does a round:
  - doors open late (the existing check);
  - water running (the sound model);
  - lights left on in rooms that should be dark (the light sensor);
  - gadgets that have gone quiet, and the garden station's readings.
- In the morning, a short report, only if there is something worth saying.
- It never closes or switches anything unless a gadget for that exists and the owner has approved it.
- The same round covers "while you're away, watch the house". It watches and tells people through the notices; it never scares anyone.

## 2. Gadgets from the workbench, used as senses and limbs
Each gadget is a device-kit config plus a part card or two, so it fits the workbench's small-context approach. Each gets a profile in `mine/bodies/`, like the garden station.

### 2a. Heat pump remote
- **Parts:** an ESP32, an IR LED with a transistor, and an IR receiver module.
- **Learning the remote:** Pebble asks the owner to press each button ("heat 21", "off", "fan low"), records the signal's timings, and plays them back.
- **Using it:** "It's cold in here." Its own air sensor agrees, so it turns the heat pump on, or offers to.
  - A heat pump counts as a heater: the owner approves it per device.
  - It never runs the heat pump with nobody home unless the owner allows that.
- **Checking it worked:** the room warms up, the unit's light comes on in the camera, or the unit is heard starting.
- Also works for TVs and fans.
- **Limit:** heat pump signals are long. Check that MicroPython's timing on the ESP32 is good enough to record and send them (the ESP32's RMT hardware sends them). If not, it becomes a job for the later C++ path.

### 2b. Power meter reader
- **Parts:** a light sensor module taped over the meter's flashing LED, on an ESP32. Nothing touches mains.
- The flash rate is printed on the meter (often 1,000 flashes per kWh).
- **What Pebble does:**
  - learns the house's daily pattern;
  - answers "How much power did we use today?";
  - notices odd things, as hints only: the fridge never stopping, the hot water cylinder heating at odd times, a heater left on.
- The meter box is often outside: weather, a battery, and the Wi-Fi map (1b) say whether it reaches.

### 2c. Washing and the weather
- **Parts:** a vibration sensor on the washing machine or dryer. "Done" means the shaking has stopped for a few minutes after a long run.
- **Weather:** the barometer's existing storm hint, and the garden station's rain and humidity readings.
- "The washing's done." "The washing's on the line and rain's coming in about an hour."
- Pebble only knows the washing is on the line if someone tells it ("I've hung the washing out").

### 2d. Door, letterbox and garage
- **Doorbell:** a button on an ESP32. Pebble goes to the door to look and says who it is if it knows them. For anyone else it says "Someone's at the door." It never opens anything.
- **Letterbox:** a reed or tilt switch on the flap, on a battery with deep sleep. Letterboxes are often out of Wi-Fi range, so it may need a relay ESP32 in between (ESP-NOW).
- **Garage door:** a reed switch that reports open or shut, checked on the bedtime round ("The garage is still open"). Opening or closing it is a limb that could hurt: the owner approves it, otherwise Pebble only reads it.

### 2e. Plant probes
- **Parts:** capacitive soil moisture sensors (not the cheap two-prong kind, which corrode), one per pot or group, on an ESP32's analogue pins. The board cards already warn which analogue pins stop working with Wi-Fi on.
- **Photos over time:** each plant photographed from the same remembered spot, so Pebble notices drooping or yellowing before people do.
- This becomes the "looking after the plants" responsibility (agency plan, 3c). Pebble reminds people to water; it can't water by itself. A pump gadget would be a limb that could hurt, near electronics and water, so it needs the owner's approval.

### 2f. Bench tools
- **Logic analyser and serial sniffer:** a spare ESP32 or Pi Pico set up to capture serial, I2C or SPI lines at modest speeds. Pebble decodes them and explains: "The sensor never answers at 0x76." The Pico's PIO hardware is good at this, and MicroPython supports it.
- **Reading the multimeter:** the display read through the camera with the workbench's OCR.
- **Resistor colour bands:** read from a photo in plain code. Colour is hard under warm light, so Pebble says how sure it is.

### 2g. Home Assistant format
- As an option, the device home also announces Pebble's gadgets in Home Assistant's MQTT format, so anyone who already runs Home Assistant sees them there.
- Off by default; home network only. This matters for other builders once the project is published.

## 3. For people

### 3a. Teaching electronics
- **A "let's do it together" mode** for any workbench playbook:
  - Pebble explains each step in plain words before doing it;
  - it asks a question now and then;
  - the learner does the wiring, and Pebble checks it from photos (the wiring check, workbench sections 4 and 9).
- **Starter projects,** each a playbook with a lesson card: blink an LED, read a button, read a temperature, make a night light.
- It remembers each learner's progress in people memory.
- **For children:** low voltage only, and a grown-up for the soldering iron.

### 3b. Helping someone build their own Pebble
- It walks a builder through the build guide one step at a time.
- It checks photos of their wiring against the schematics.
- It flashes the body firmware over USB (workbench), runs the body's self-test, then a first drive with the wheels off the ground.
- **The new Pebble starts with a new, empty self.** Pebble never copies its own self, memories or birth record into another one.

### 3c. Kids
- **Reading practice:** the child reads a book aloud. Pebble reads the page with OCR, follows along with what it hears, and helps with a word the child is stuck on. Kind and patient, never harsh.
- **Times tables and spelling** on its face, by voice.
- **Made-up bedtime stories** with its own drawings (drawing and the scene language exist).
- **"Why?" questions** answered from the offline Wikipedia pack (storage plan), in child-sized words.
- **Limits:**
  - speech recognition is weaker on children's voices; measure it;
  - a child is its own trust tier, and that gate still decides what a child may ask.

### 3d. In the kitchen
- **Recipes** from the Wi-Fi inbox, or a photo of a recipe card read with OCR.
- Read one step at a time, waiting for "next", "say that again" or "how much flour?".
- Named timers that come and find you (1a).
- Unit conversions from the calculator (workbench, section 10).

### 3e. Someone living alone
- A Pebble for a grandparent, for example:
  - a daily hello and reminders (1a);
  - the existing "someone on the floor" and "calling for help" checks;
  - with the owner's switch on, a notice to family through the existing notices if nobody has been seen by a set time.
- The notice says only that nobody has been seen, never pictures or sound.
- It says plainly that it is not a medical alert, and it never calls emergency services (an existing decision).

### 3f. Translating for a visitor
- Short spoken translation between two people: Pebble hears one, translates, and speaks to the other.
- **Models:** Opus-MT, one small model per language pair (CC-BY-4.0, with credit). Meta's NLLB is non-commercial, so it can't be used.
- **Limits:**
  - only languages it has offline speech recognition and a voice for;
  - a delay of a few seconds.

### 3g. Photos and time-lapse
- **A group photo with a self-timer:** Pebble backs up until everyone fits and counts down on its face.
- **Time-lapse** of a plant, a print or a sunset, from a spot it remembers.
- Photos of people: "Should I keep these?" They are only shared through `pebble.local` with the code, like the inbox.

## 4. 3D printing (the owner has a printer)

### 4a. Cases for the gadgets it builds
- Board and part cards gain outlines, hole positions and connector positions.
- **A case maker** with a few settings:
  - a box and lid, with standoffs;
  - cut-outs for USB and sensors;
  - vents for air sensors;
  - a wall hook, or a stake for the garden.
- It follows the same approach as `cad/` (Python and manifold3d), with a fit check.
- Pebble hands the STL over through `pebble.local` and shows a picture of it on its face.
- **To check:** whether manifold3d runs on the phone under Chaquopy. If it doesn't, ready-made case pieces with a few measurements will do.
- **Outdoor cases:** PLA softens and warps in the sun, so Pebble suggests PETG or ASA for those.

### 4b. Watching prints
- A camera on the printer: an ESP32-CAM that Pebble sets up, or Pebble parked looking at it.
- It spots failed prints (spaghetti, a print come loose) and tells the owner.
- If the printer has a local control page (OctoPrint or Klipper's Moonraker) and the owner allows it, Pebble may **pause** a failed print. It never starts a print or heats anything.
- **Licence:** Obico's open failure detector is AGPL-3.0, which is copyleft. The plan is a model made here instead, which would join the tracked made-here models.
- **Not shippable:** iFixit's repair guides (CC BY-NC-SA, non-commercial).

## 5. What this body can't do
- **No arm:** no fetching, carrying, pressing buttons or watering. A gripper could come with `new-bodies.md`.
- **No stairs,** and 0.25–0.3 m/s, so crossing a house takes a while.
- **No internet:** no forecasts, news or web answers. The barometer and the garden station are its weather.

## Licences
| Thing | Licence | Use it? |
| --- | --- | --- |
| Opus-MT translation models | CC-BY-4.0 | Yes, with credit |
| Meta NLLB translation | CC-BY-NC-4.0 | No: non-commercial |
| Obico print-failure detector | AGPL-3.0 | Flagged: copyleft; make one here |
| iFixit repair guides | CC BY-NC-SA | No: non-commercial |
| Home Assistant's MQTT format | A format; Home Assistant is Apache-2.0 | Yes |
| MicroPython, including the Pico's PIO | MIT | Yes |

## Open questions for the owner
- **Messages:** who may send to whom, whether children can send, and how long an undelivered message is kept before the sender is told.
- **Heat pump:** may Pebble turn it on by itself when the room is cold, or only offer?
- **Living alone:** what time the "nobody seen" notice goes, and to whom.
- **Bedtime round:** every night, or only when asked?
- **Desk buddy:** off until someone asks for it (suggested), or on for the owner?
- **Printer:** may Pebble pause a failed print?

## Build order
Most value for the least work first. These come after the workbench's device home is built, because many of them use it.
1. Messages, reminders and timers that come and find you. Needs the agency plan's responsibilities and promises book.
2. House maps, Wi-Fi first. Needs the time-series store (workbench, step 9).
3. Heat pump remote.
4. Washing and the weather.
5. Teaching mode on the workbench playbooks.
6. Bedtime round and morning report, desk buddy, dropped-part finder.
7. Plant probes; door, letterbox and garage; power meter.
8. Kids, the kitchen, someone living alone, photos.
9. Bench tools and the Home Assistant format.
10. Cases for gadgets, and watching prints.
11. Translation, and helping build another Pebble.

## Tests
- **Messages:**
  - delivered to the right person when several are there;
  - never said in front of others unless the sender asked;
  - an undelivered message is reported to the sender;
  - a stranger can't send one;
  - an alarm beats a reminder on the laws' ladder;
  - a timer comes to whoever set it.
- **House maps:** in the sim building, readings land on the right cells, a damp room and a weak Wi-Fi spot are flagged, and nothing is said before there is enough data.
- **Heat pump:** with no owner approval, nothing is sent; with nobody home, nothing is sent unless allowed; a recorded signal plays back the same timings.
- **Washing:** "done" only after a long run then stillness; the rain warning only when the washing is known to be out.
- **Bedtime round:** the report lists only what was found, and quiet hours are kept.
- **Teaching:** each starter playbook runs end to end against the fake `machine` module, with the explanations in plain words.
- **Building another Pebble:** the new self starts empty, and nothing from Pebble's own self is copied.
- **Kids:** reading practice follows a page read by OCR, and the child trust tier gates every request.
- **Printing:** Pebble can pause but never start or heat a print.
