# More everyday value for the household

The owner's question, 19 October 2026: "Based on the sensors the phone has and the sensors we can add to some of Pebble's bodies and/or on Pebble's abilities and what we can set it up to do (like what we did with the Raspberry Pi programming), what other value can Pebble immediately provide to people in the house?"

This report lists new things Pebble could do for a household. It leaves out what is already built (the safety notices and alarm ladder, room air, things memory and "where is", doings and routines, the pet bowl, the door at night, rooms, follow/come/go to, the face, drawing, speech) and what is already planned (`plans/everyday-uses.md`, `plans/workbench.md` and the rest). Each idea says which part it builds on. Reading moods and body language (`plans/reading-people.md`) and responsiveness are out of scope.

Nothing here has run on the phone. Every speed, range and accuracy is an estimate until measured on the Pixel 6 Pro.

## Owner's answers (19 October 2026)
1. **When:** the household pack is built right after Android round 3.
   - The pack is A1–A15 and A17, plus A16 if the phone gives two raw microphone channels, plus the climate round (answer 8).
   - Now that navigation is fixed, the driving parts come too: the chirp finder, the quake round and hide and seek.
   - A18 is low value and comes last.
2. **Night knocks:** a single knock is noted quietly for the morning. Three knocks within two minutes are told at once to the owner or the inner circle. Pebble never opens the door.
3. **Cooking watch:** on by default, and it repeats. After 5 minutes with cooking still heard or seen and nobody in the kitchen, Pebble says so, then again every 5 minutes until someone is back or the cooking stops.
4. **Lists:** everyone in the household, children included, may add and read. Strangers can do neither.
5. **"While you were out":** only the house, pets, the door and the listener's own things. Never one adult's comings and goings to another. Children's arrivals go to their parents only if the owner turns it on.
6. **Captions and visitors mode:**
   - Captions show only while the person who asked for them is there.
   - Pebble offers visitors mode when it sees three or more people it doesn't know, and trusted people switch it on and off.
7. **Tsunami line:** asked once at setup. It stays off until the owner says the house is in a tsunami zone.
8. **No Bluetooth sensors.** Pebble goes to each room and measures it itself, with the BME688 on board: a **climate round**.
   - It drives to each known room when idle and charged enough, waits for the reading to settle, and keeps a room-by-room log of temperature, humidity, dew point and air.
   - Limit, said honestly: this can't measure the fridge, the freezer or outdoors, and a reading is only as fresh as the last visit.
9. **Thermal camera:** not now.
10. **CO sensor:** no. Pebble suggests a certified CO alarm where there is gas, a wood burner or an attached garage, and keeps listening for alarms.
11. **Microphones in other rooms:** none.
12. **Games without a grown-up home:** all games, hide and seek included, with the usual speed caps and gaps near children.
13. **Zigbee:** skipped.
14. **Key tags and "I'm OK" buttons:** skipped for now.

## The short answer
- **The microphones are the biggest untapped sense.** The sound model already scores knocks, doorbells, microwaves, phones ringing, rain, boiling and sizzling pans, a cat meowing and a dog whimpering every half second, and already makes a 1,024-number description of every second of sound. Pebble only listens to the alarm and baby-type sounds today. Using the rest needs plain code, not new models.
- **Bluetooth is the cheapest big jump.** The phone can read cheap thermometers, buttons and key tags straight from the air, with nothing to build or flash. About NZ$100 buys head-height temperatures in four rooms, outside and in the freezer, plus three key tags that beep when asked.
- **The body has no free pins.** All 15 edge pins of the body's ESP32 are taken (`interfaces.md`, pin map), and its one I²C bus carries the safety sensors. New body sensors belong on a small "backpack" board with its own chip, which Pebble can build and flash itself (`plans/workbench.md`). Room sensors belong in the dock or in gadgets.
- **Some phone parts give little:** the magnetometer, the flicker sensor (apps can't read it), the proximity sensor beyond today's use, and NFC on this body (the phone's back faces backwards inside the yoke). UWB is real but awkward: on Pebble's sideways mount the one angle the Pixel 6 Pro measures points up and down, not left and right.

## Ranked, by value to the household now

Effort: **S** is a day or two of agent work, **M** about a week, **L** several weeks. "Needs nav" means it drives around the house, so it waits for the navigation fixes in `STATUS.md`. AliExpress prices are in NZ$ and **exclude GST** (15 % is added at checkout); they were read on 19 October 2026 and swing a lot between sellers.

### A. Software only, today's hardware (no purchase)

| # | Idea | What the person gets | Today, software only? | Effort | Main risk | Builds on |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Sounds that matter | "Someone's knocking at the door", "the microwave's done", "it's started raining", said where you are | **Yes** | S–M | Knock-like sounds (cupboards, footsteps, TV) | Hearing, safety notices; everyday-uses 1a, 2c, 2d |
| A2 | Unattended cooking watch | "The pan's still sizzling and nobody's been in the kitchen for 5 minutes" | **Yes** | M | Silent hobs and ovens are missed; must never sound like "it's safe" | Doings, hearing, safety ladder |
| A3 | Household lists and a short noticeboard | "Add milk to the list"; the list handed to your phone as a QR code before you leave | **Yes** | S–M | Misheard items; screen burn-in | Everyday-uses 1a; Wi-Fi inbox; occasions |
| A4 | Teach Pebble a sound | "This is the washing machine finishing" → "The washing's done" every time | **Yes** | S–M | Only works within earshot | Hearing (YAMNet's numbers, already made) |
| A5 | Find the chirping smoke alarm; the monthly alarm test | "It's the hallway one chirping; that usually means a low battery"; a record of which alarms sounded | **Yes** (finder needs nav) | M | Test mode must never hide a real fire | `hearing/alarm.py`, ladder, 1a |
| A6 | Sound to sight, and captions | For someone hard of hearing: Pebble comes and shows DOOR, MICROWAVE, BABY or their name; live captions on request | **Yes** | M | Slow to cross the house; not a certified visual alarm | Ladder, listening, A1 |
| A7 | Torch and night light | "Pebble, light" in a power cut; a soft glow at night | **Yes** (check the torch with the front camera on) | S | Phone heat | Power cut notice; agency 3b |
| A8 | After a big earthquake | How long it lasted, "long or strong, get gone" if the house is in a tsunami zone, then a check-in round | **Yes** (round needs nav) | S–M | Must never sound like an official warning | Earthquake notice, ladder |
| A9 | House care calendar and offline almanac | "Test the smoke alarms today?", "clocks go forward tonight", sunset and curtains, Matariki | **Yes** | S | Nagging | Everyday-uses 1a, occasions |
| A10 | Condensation line from today's air sensor | "Any window colder than 13 °C will run wet tonight" | **Yes** | S | Humidity drift | Everyday-uses 1b (damp) |
| A11 | While you were out, and "did I already?" | "A knock at 2:15, the washing finished at 3, the power was off 10 minutes"; "You told me you took them at 8:12" | **Yes** | S–M | Becoming a tracker of other adults | Black box, 1e, 1a |
| A12 | Pets while people are out | "The cat's meowing at the back door"; "Rex howled for 40 minutes after you left"; the water bowl | **Yes** | S | None big | Pets |
| A13 | Games | Red light green light, musical statues, dice and scores, Simon says; hide and seek later | **Yes** (hide and seek needs nav) | M | Children running near a robot | Play, body points |
| A14 | Visitors mode and a guest Wi-Fi card | No new prints or overheard facts while guests are over; a QR code to join the guest network | **Yes** | S | Showing the wrong password | People and trust, sealed self |
| A15 | The house's emergency facts | "Where's the water shut-off? The getaway bag? The extinguisher?" | **Yes** | S | Only as good as it was told | Things memory, show and tell |
| A16 | Which way a sound came from | Pebble turns to a knock or a crash it can't see; finds beeping tags and chirps faster | **Check first** (two raw mic channels) | M | Android may not give raw stereo | Hearing, attention |
| A17 | Eyes for someone who can't see well | "Is the light on?", "What does the whiteboard say?" from across the room with the 4× lens | **Yes** | S–M | Reading from 15 cm off the floor | Picture questions |
| A18 | Noise diary and Wi-Fi drop log | Rough loudness by the hour; "the router dropped out at 2:10" | **Yes** | S | No evidence value | Hearing level, link |

### B. With a cheap part

| # | Idea | What the person gets | Part and rough cost | Where it goes | Effort | Main risk | Builds on |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | Bluetooth thermometers, read straight from the air | Head-height temperature and humidity in each room, outside, fridge and freezer; frost and freezer-thaw notices | Inkbird IBS-TH2 NZ$18–24; Shelly BLU H&T about NZ$45 | Rooms, outside, freezer | S–M | Freezer walls block radio | Everyday-uses 1b, 2c, 2e |
| B2 | Key tags that beep | "Find my keys": the tag beeps and Pebble homes in on it | "iTag" tags NZ$2–5 | Keys, remote, wallet | M (needs nav) | Clones differ | Things memory |
| B3 | Thermal camera backpack | Draughts, cold spots and mould-risk surfaces; heater or oven on in an empty room; a hot power board; someone on the floor in the dark | MLX90640 NZ$48–68 + ESP32-C3 NZ$3–6 | Backpack on the head or body front | L | Shiny metal reads wrong | 1b, A2, A10, someone on the floor |
| B4 | The dock as a hub | CO₂ ("the lounge got stuffy"), presence without a camera, power-cut news even when Pebble is away | SCD41 NZ$22–35, LD2410C NZ$5–9, ESP32-C3 NZ$3–6; PMS5003 NZ$20–30 optional | The dock | M | CO₂ is not CO; fake modules | Workbench device kit |
| B5 | Leak probes | "Water under the washing machine!" | ESP32-C3 + two probes + 2 × AA, about NZ$8–12 | Laundry, dishwasher, cylinder, sinks | S–M | Only where a probe is | Device kit, 1e |
| B6 | Room presence radar | "Is anyone in the spare room?"; heater on in an empty room; a camera-free "movement this morning" | LD2410C NZ$5–9 + a USB plug | Rooms | S–M | Default Bluetooth password | 3e, 1e |
| B7 | "I'm OK" and "come here" buttons | One press answers the daily check-in; a long press calls Pebble | Shelly BLU Button Tough NZ$18–33 | Bedside, bathroom | S | Not a panic button | 3e |
| B8 | Mobile IR remote | Pebble works the TV, heat pump or fan in whatever room it's in | IR LED + receiver NZ$2–4 | The backpack | M | Aiming from the floor | Everyday-uses 2a |
| B9 | Pebble's voice and alarm ears in far rooms | "Dinner's ready" said in the bedroom; the smoke-alarm pattern heard in the garage | ESP32-S3 + MAX98357A NZ$2–6 + speaker; INMP441 mic NZ$2–7 | Far rooms | L | A microphone in a bedroom | 1a, hearing |
| B10 | Meat thermometer | "The roast is at 63 °C", told to the cook at the target | A readable Bluetooth probe, about NZ$50+ | Kitchen | S | Only some models are readable | 3d kitchen |
| B11 | Notes that stay up | An e-ink board on the fridge; battery-free labels Pebble writes | 2.9" e-paper NZ$11–14; NFC e-paper cards NZ$24–57 | Fridge; freezer boxes | M | Reaching the back of Pebble's head | A3, workbench |

### C. Later

| # | Idea | What it would give | Why later |
| --- | --- | --- | --- |
| C1 | Zigbee through a Pi that Pebble sets up | Door, leak, motion and button sensors at NZ$6–12 each, and power-metering plugs | Needs the workbench's Pi path and an offline package store; dongle NZ$18–23 |
| C2 | UWB anchors in the dock | Distance to the dock to about 10 cm, in the dark, anywhere in range | Anchors about NZ$50 each before GST; Android pairing reports are mixed; distance only on this mount |
| C3 | A microphone-array gadget | Sound direction if the phone can't give two channels | Only if A16 fails |
| C4 | Power-metering smart plugs | "The dehumidifier used 4 kWh this week"; switching a heater off | They are limbs that could hurt; owner approval per device |
| C5 | A door camera | "A parcel's on the doorstep" | Films the street and visitors; heavy privacy |
| C6 | Wi-Fi ranging to ESP32 gadgets | Rough position from Wi-Fi timing | Errors of metres; not worth it |
| C7 | A real carbon monoxide sensor | A CO number as a hint | Recommended **no**: false comfort (see C7) |
| C8 | NFC tags in each body's head mount | The phone knows which body it's in before any link | Only matters with several bodies (`new-bodies.md`) |
| C9 | Tide tables | High and low tide for the nearest port | Only coastal households; a yearly data file |

## Pieces several ideas share
- **A sharp layer over the face.** The face page draws a canvas only 32 pixels tall (`brain/pebble/web/page.html`), which can't show a list, a caption or a scannable code. A text and image layer over it unlocks A3, A6, A14 and parts of A9 and A11. The page is one self-contained file with a strict content policy, so the QR encoder must be plain code inside it.
- **Screen burn-in.** The Pixel 6 Pro has an OLED screen. A still image left for hours can burn in. Lists, codes and boards show for about 30 seconds, then the face comes back. The e-ink board (B11) is the always-on version.
- **New notice kinds go through the existing ladder** (`safety/ladder.py`): one incident per kind, quiet hours, who may say it's fine, the black box. Appliance and door notices are low notices, like "baby crying" today. Only fire, CO, help, someone on the floor, glass, quakes and (new) water leaks are never held back.
- **A Bluetooth listener** in the Android app (passive scan, then parsers per sensor family) serves B1, B2, B6, B7 and B10. It costs almost no processor time. Android stops unfiltered scans while the screen is off, so it scans with filters for the sensor families it knows.
- **The ladder rule.** Most of section A reads numbers the phone already computes (YAMNet's scores and embeddings, the words recognised, the body points). Each idea below states what it adds on the Pixel 6 Pro. Nothing here needs a bigger model.

## What each phone part can still give

| Part (Pixel 6 Pro) | Used today | What it could add | Verdict |
| --- | --- | --- | --- |
| 3 microphones | One 16 kHz feed: words, the alarm patterns, YAMNet | Door, phone, appliance and rain sounds (A1), taught sounds (A4), chirp finding (A5), direction from two mics (A16) | The biggest untapped sense |
| Stereo speakers | Voice, alarm sound | Fine as is; far rooms need B9 | — |
| Front camera (94°) | People, things, posture, floor scan | Games (A13) | Mostly used |
| Rear wide (82°), ultrawide (114°), 4× tele (23.5°) | The dock tag | Reading across a room (A17); Pebble turns round to use them | Small win |
| Rear LED (torch) | Not used | Torch and night light (A7) | Small win |
| Light sensor | Lights out, dark, flicker hint | "Is the light on?" (A17), sunset checks (A9) | Small |
| Spectral and flicker sensor | — | Google lists it beside the rear camera, but Android has no public sensor type for it, so assume apps can't read it. Check once with the full sensor list on the phone | Nothing to plan |
| Proximity | Pokes hold the wheels | — | Done |
| Accelerometer, gyro | Quakes, being picked up, navigation | How long a quake lasted (A8) | Small |
| Barometer | Floors, door pulses, storm hint | — | Done |
| Magnetometer | Streamed (`safety/feeds.py`), not used | Too disturbed indoors for a compass; at most a place print for navigation (pebble-nav's call) | Skip |
| NFC | Not used | Reads and writes tags held to the back of the head. On this body the phone's back faces backwards inside the yoke, so it's awkward. Uses: battery-free labels (B11), a tag in each head mount (C8) | Low |
| UWB | Not used | Distance to a FiRa anchor. Google's library lists the Pixel 6 Pro (foreground only, which suits Pebble). The one Pixel 6 Pro capability log found reports distance and azimuth but no elevation; mounted sideways, that azimuth points up and down. Anchors cost about NZ$50 | Later (C2) |
| Bluetooth 5.2 | The body link | Reads sensors and tags with nothing to build (B1, B2, B6, B7, B10) | The biggest cheap win |
| Wi-Fi 6E | The body link, gadgets | Signal map (planned in 1b); router-gone log (A18); Wi-Fi ranging is too rough (C6) | Small |
| OLED screen | The face | Lists, codes, captions, night light, through the sharp layer | Mind burn-in |

## A. Software only, today's hardware

### A1. Sounds that matter
- **What you get:** "Someone's knocking at the door", said where you are, even in the shower or at the back of the house. Also "the microwave's done", "a phone's ringing in the lounge", "it's started raining" (when someone said the washing is out), "an alarm clock's been ringing for 5 minutes".
- **How:** YAMNet already gives a score every half second for each of these: Knock, Doorbell, Ding-dong, Microwave oven, "Beep, bleep", Ding, Buzzer, Telephone bell ringing, Ringtone, Alarm clock, Rain on surface, Thunder, Whistle and Steam whistle (kettles), Boiling (`brain/pebble/hearing/models/yamnet_class_map.csv`). Plain code turns them into notices with a score and a time, like the table under "Hearing" in `brain/README.md`. "Tell me when the microwave's done" makes Pebble come to that person (1a's messages).
- **Ladder:** nothing new runs; plain code reads scores that are already made.
- **Limits:** only what reaches the phone. A knock through two closed doors is faint. Cupboard doors, footsteps and the TV make knock-like sounds, so a knock needs two or three in a row. Pebble never opens the door and only names who is there if it sees and knows them. Thresholds must be tuned on real recordings (clear-licence ones, as for the alarm tests) and in the real house.
- **At night:** a knock is noted. Repeated knocking (three times in two minutes) is told at once to a trusted adult. Open question below.
- **Privacy:** no sound is kept; the black box keeps "a knock at 14:12".
- **Builds on:** Safety notices and Hearing; everyday-uses 1a (timers), 2c (washing and weather) and 2d (doorbell). The doorbell gadget stays for a door out of earshot.

### A2. Unattended cooking watch
- **What you get:** "Ina, the pan's still sizzling in the kitchen and nobody's been there for 5 minutes." Once per cooking session, never a nag.
- **Why it matters:** Fire and Emergency NZ calls unattended cooking the leading cause of house fires in New Zealand, and says one in four house fires starts in the kitchen.
- **How:** doings already reads "cooking" (a stove, pan or kettle near someone) and "leaving". YAMNet scores Frying (food), Sizzle and Boiling. If cooking sounds go on while nobody is seen in the kitchen for a set time, Pebble finds the cook, or the nearest trusted person. If it sees smoke or hears the smoke alarm, the existing ladder takes over.
- **Ladder:** none new.
- **Limits:** induction hobs, ovens and gentle simmers are often silent. Pebble hears only from nearby rooms. It can't tell a stew someone meant to leave from a forgotten pan, so it only mentions it, once. **It is not a smoke alarm and never says the kitchen is safe.** The thermal camera (B3) makes this much better, because a hot hob or oven door shows up whether or not it makes a sound.
- **Builds on:** doings, hearing, the ladder.

### A3. Household lists and a short noticeboard
- **What you get:**
  - Anyone at home says "add milk to the shopping list", "we're out of dishwasher tablets" or "put 'fix the gate' on the to-do list".
  - "What's on the list?" is read out.
  - "I'm going to the shop" gets the list as a QR code on the face. A phone camera reads it as plain text: no internet, no app, nothing to install.
  - When someone walks up, a short board for about 30 seconds: messages waiting (1a), today's reminders, birthdays (`occasions.py`), how many things are on the list.
- **How:** a new request kind "list" (add, remove, read, clear), stored sealed in the self. The QR code is drawn on the sharp layer. The same list is at `pebble.local` behind the inbox code, for printing.
- **Ladder:** none.
- **Limits:** speech recognition mishears ("thyme" and "time"), so Pebble reads back each item it adds. A QR code holds about 1–2 kB, so a long list splits into two codes. Burn-in: the board never stays up.
- **Privacy:** household lists are for everyone in the household; strangers can't add or read. Personal lists are an option.
- **Builds on:** everyday-uses 1a (messages), the Wi-Fi inbox (agency plan, section 2), workbench section 10 (units).

### A4. Teach Pebble a sound
- **What you get:** "Pebble, this is the washing machine finishing." From then on: "The washing's done." The same works for the dryer's buzzer, the dishwasher, the bread maker, the gate latch, the cat flap or a particular doorbell tune.
- **How:** the YAMNet file Pebble ships already outputs 1,024 numbers that describe each second of sound (`embeddings`, made by `tools/export_yamnet.py`). The brain reads only the scores today (`hearing/yamnet.py` picks `scores`). Pebble keeps three to five examples of each taught sound, as numbers only, sealed, and matches new sound against them with a safety margin. It asks for a second example before trusting the first, and says how often it was right.
- **Ladder:** no new model; some tens of thousands of multiplications every half second, nothing next to the model itself.
- **Limits:** the tune must reach the phone. Laundries are often behind a closed door; then the vibration gadget (2c) is still the answer. Two machines that play the same tune confuse it, and it asks.
- **Builds on:** hearing; everyday-uses 2c.

### A5. Find the chirping smoke alarm, and the monthly test
- **What you get:**
  - "One of the smoke alarms is chirping about every 40 seconds. That usually means its battery is low."
  - "Find it": Pebble goes room to room, listens to two or three chirps in each, and says "I think it's the one in the hallway. It was loudest there."
  - "We're testing the alarms": Pebble listens while you press each test button, writes down which ones it heard and from where, and offers to remind you next month. Fire and Emergency NZ advises testing every alarm each month.
- **How:** the beep detector already measures 23 narrow bands between 2.4 and 4.6 kHz every 20 ms (`hearing/alarm.py`). A third pattern joins the two it knows: one short beep, then a long, steady gap, repeating. Loudness per spot (and direction, if A16 works) picks the alarm. The eyes can look up for it.
- **Ladder:** the detector is already running.
- **Limits:**
  - A test proves only that the sounder works, never that the alarm senses smoke.
  - Chirps echo, so "loudest" can be wrong between two alarms close together. It takes about a minute per spot.
  - Low-pitched (520 Hz) alarms are outside its band.
  - A chirp can also mean end of life; the alarm's manual says which.
- **Test mode must never hide a real fire.** Only a trusted person can start it. It ends by itself after 10 minutes. An alarm that keeps going for more than 30 seconds, or smoke seen, still counts as real.
- **Builds on:** `hearing/alarm.py`, the ladder, 1a reminders. The finder needs nav.

### A6. Sound to sight, and captions
- **What you get:** for someone deaf or hard of hearing, or anyone in headphones or another room, Pebble comes to them and shows what it heard in big letters: DOOR, MICROWAVE, BABY, PHONE, or their name, with a small wiggle. Alarms keep their flashing screen. On request, live captions of what others in the room are saying.
- **How:** any notice kind (A1, A4 and today's) can be sent to a named person "by sight". Captions come from the words speech recognition already makes for its rolling window, shown on the sharp layer.
- **Ladder:** none new; captions reuse recognition that is already running.
- **Limits:**
  - At 0.25–0.3 m/s it takes a minute or more to cross the house.
  - **It is not a certified visual smoke alarm.** A household with a deaf member needs strobe or vibrating alarms.
  - Captions are only as good as the recognition, which is weaker far away and with several people talking.
- **Privacy:** captions show only what everyone in the room just heard, never earlier lines, and "between us" lines never. Nothing is kept. They are on only when the person who asked for them is there.
- **Builds on:** the ladder, listening and talking, 1a.

### A7. Torch and night light
- **What you get:** "Pebble, light." In a power cut it comes to you with the torch on and lights the way. A soft, warm screen glow at night for a child who is scared of the dark.
- **How:** the rear camera's LED, through Android's torch call. Pebble turns its back to aim it. It already notices a power cut (lights out and the charger stopping at once) and can offer the light.
- **Ladder:** no processor time. The LED warms the phone, so the torch has a time limit and law 3's heat rules apply.
- **Limits:** check on the phone that the rear torch works while the front camera is in use. Driving in the dark is slower and less sure; the floor scan sees less.
- **Builds on:** the power cut notice; agency plan 3b (running flat).

### A8. After a big earthquake
- **What you get:** when the shaking stops, Pebble says how long it lasted. If it went on for more than a minute, or was strong, and the owner has said the house is in a tsunami zone: "That was long. The advice near the coast is: long or strong, get gone." Then it goes to each person it knows is home and asks "Are you okay?", and tells the owner (or the notice) who it couldn't find.
- **How:** the quake check already exists (while docked, shaking sustained for 4 seconds); it gains a duration. The round uses the ladder's "find people".
- **Ladder:** none.
- **Limits:**
  - Pebble sits on wheels and a magnetic dock, so strength is rough.
  - **It is not a warning system.** People's own phones get Emergency Mobile Alerts; Pebble doesn't.
  - It never says a tsunami is coming; it repeats Civil Defence's own rule.
  - After a quake the floor may have broken glass, so it drives slowly behind the floor scan.
- **Builds on:** the earthquake notice and the ladder. The round needs nav.

### A9. House care calendar and offline almanac
- **What you get:**
  - "It's the first of the month. Shall we test the smoke alarms?"
  - "The clocks go forward tonight."
  - "Matariki is this Friday."
  - "Sunset is at 6:12." On cold days, with EECA's advice credited: closing curtains before dark keeps the heat in.
  - "Time to check the emergency water?" Get Ready says at least 3 litres a person a day, for at least three days.
  - Sunrise, sunset and the moon, for children.
- **How:** plain code. Sun and moon times come from the date and the town (the owner sets it once). Daylight saving comes from the phone's time-zone rules. NZ public holidays come from fixed rules plus the Matariki dates set in law to 2052. Each house job is offered once and becomes a repeating reminder (1a).
- **Ladder:** none.
- **Limits:** a wrong town gives wrong times. Holiday rules can change. Each job is offered once; "no thanks" is remembered.
- **Builds on:** everyday-uses 1a, `occasions.py`.

### A10. A condensation line from today's air sensor
- **What you get:** "Tonight, any window colder than 13 °C will run wet." And "the air in the lounge is holding a lot of moisture today."
- **How:** the dew point, worked out from the BME688's temperature and humidity in plain code. For example, 20 °C at 65 % gives a dew point of about 13 °C. The dew point is nearly the same across a room even when the temperature isn't, and the robot's own warmth doesn't change it. So the low, self-warmed sensor is fair for this, though not for the room's temperature.
- **Mould is about surfaces.** The usual rule is that a surface staying above about 80 % humidity grows mould (ISO 13788, IEA Annex 14). Without a surface temperature Pebble can only talk about the air and the windows. With the thermal camera (B3) it can map the surfaces. With an outside thermometer (B1) it can forecast how cold the glass will get tonight.
- **Ladder:** none.
- **Limits:** humidity sensors drift a few percent. Pebble is not a building inspector.
- **Builds on:** everyday-uses 1b (damp).

### A11. While you were out, and "did I already?"
- **What you get:**
  - When someone comes home, and only if something happened: "A knock at 2:15, and nobody answered. The washing finished at 3. The dog howled on and off for 20 minutes after you left. The power was off for 10 minutes."
  - "Did I take my 8 o'clock pills?" gets "You told me you took them at 8:12."
- **How:** the notices and the black box already record events. A summary is made for the person who arrives, through the privacy filter. The "did I" log keeps only what people told Pebble, never what it guessed by watching.
- **Ladder:** none.
- **Limits:** Pebble knows only what reached its senses. The pill log is not a medical record. Pebble never says whether to take a dose, and says "I don't know" when it doesn't.
- **Privacy:** Pebble doesn't report one adult's comings and goings to another. Children's arrivals go to their parents only if the owner turns that on (decision below).
- **Builds on:** everyday-uses 1e (round and away watch), 1a, the black box.

### A12. Pets while people are out
- **What you get:** "The cat's been meowing by the back door." "Rex howled on and off for 40 minutes after you left" (told when you're home, or as a notice if notices are on). "The water bowl looks empty."
- **How:** YAMNet's Meow, "Whimper (dog)" and Howl (barking is already a notice). The bowl check gains the water bowl (a picture question at the usual time).
- **Limits:** it can't tell which pet by sound. It is not a vet. It never approaches an animal closer than the law-1 gaps (0.8 m, 1.2 m for dogs).
- **Builds on:** Pets.

### A13. Games
- **What you get:**
  - **Red light, green light:** Pebble shows closed eyes and counts while players creep forward, then "looks" and catches anyone who moves. It turns on the spot only.
  - **Musical statues:** the same check with music from its synth.
  - **Dice, coins, scores and a turn timer** for board games.
  - **Simon says** with body points.
  - **Hide and seek** later: Pebble counts, then searches the house and says "Found you, Sam!"
- **How:** the eyes already give body points; movement between frames means "moved". Dice use the chaos dial's logged random streams, so they're fair and checkable. Hide and seek uses nav and finding people.
- **Ladder:** body points run at a game rate (about 5 a second) only during a game, and drop to 2 a second when the phone is warm.
- **Safety:** children run towards a robot, so Pebble doesn't drive in the turn games. In hide and seek it keeps the crawling-child crawl (15 % power), never drives into tight spaces, and doesn't play in the dark. The child trust tier gates every game. **Pebble is not a babysitter or a child monitor.**
- **Builds on:** Play, gestures, body points.

### A14. Visitors mode and a guest Wi-Fi card
- **What you get:** "We've got people over tonight." Pebble then makes no new face or voice prints, keeps no overheard facts, and shows a small sign that it's in visitors mode. A guest who asks what it keeps gets a plain answer. "Show the guest Wi-Fi" puts up a QR code that phones join with.
- **How:** switches on existing stores; the code on the sharp layer. The owner gives the guest network's details once, and they are sealed with the self.
- **Limits:** the guest network only, never the main password. Safety notices still work for guests: law 1 comes first.
- **Builds on:** people and trust, the sealed self, listening.

### A15. The house's emergency facts
- **What you get:** "Where's the water shut-off?", "Where's the switchboard?", "Where's the getaway bag?", "Where's the fire extinguisher?" Pebble says, and leads people to the ones inside. A house-sitter or new flatmate gets the same answers.
- **How:** the owner shows or tells it once ("this is the switchboard"); things memory plus told facts. A yearly reminder to check they're still right.
- **Limits:** only as good as what it was told.
- **Builds on:** things memory, show and tell.

### A16. Which way a sound came from (check first)
- **What you get:** Pebble turns towards a knock, a call or a crash it can't see. Beeping tags (B2) and chirps (A5) are found faster.
- **How:** on Pebble's sideways mount the phone's top and bottom microphones sit at its left and right ends, about 15 cm apart. If Android gives two raw channels, the tiny time difference between them says left or right (a standard method called GCC-PHAT, in plain code).
- **Check first:** whether the Pixel 6 Pro gives two unprocessed channels (`AudioRecord` in stereo with the unprocessed source, then read the channel count). Phones often hand over processed stereo, which may blur the timing.
- **Ladder:** small; one short sound transform every 30 ms.
- **Limits:** front and back sound the same (it turns and listens again); echoes; the direction is rough, tens of degrees.
- **Builds on:** hearing, attention, who is speaking.

### A17. Eyes for someone who can't see well
- **What you get:** "Is the light on?" (the light sensor). "What does the whiteboard say?", "What's the use-by date on this?", "What does the oven clock say?", read from across the room.
- **How:** picture questions already exist. A "look closer" step turns Pebble round and uses the rear 4× lens (23.5°, 48 MP).
- **Limits:** Pebble's eyes are 13–17 cm off the floor, so bench tops are seen from below. The reading isn't perfect and it says when it's unsure. For medicines it reads the label aloud and asks the person to check it themselves; it never advises on doses.
- **Builds on:** questions about what it sees.

### A18. Noise diary and Wi-Fi drop log
- **Noise:** rough loudness by the hour, for "how loud was it last night?". The phone's microphone isn't calibrated, so it has no value as evidence for a noise complaint, and Pebble says so. Levels only, never sound.
- **Wi-Fi:** "The router dropped out at 2:10 and came back at 2:25." Local only: Pebble never checks the internet.
- **Low value; small effort.**

## B. With a cheap part

### B1. Bluetooth thermometers, read straight from the air
- **What you get:**
  - Temperature and humidity at head height in each room, which fixes the house maps' biggest limit (the body's sensor is near the floor).
  - Outside: "It's 2 °C and falling. A frost is likely tonight." It also feeds A10's window forecast.
  - Freezer: "The freezer has been above −12 °C for two hours." Fridge too.
  - A cold room: "The baby's room is 14 °C." The World Health Organization's guideline is at least 18 °C in cold seasons; Pebble credits it and doesn't set a target of its own.
- **How:** these sensors broadcast their readings every few seconds. The phone just listens; nothing pairs and nothing is built. Formats:
  - **BTHome**, an open format (Shelly's BLU sensors and many home-made ones);
  - **Inkbird's broadcasts**, read by the open `inkbird-ble` library (the IBS-TH2 is read from its broadcasts alone);
  - **Xiaomi with pvvx's custom firmware**, flashed from a browser. The pvvx project warns that Xiaomi units made since March 2025 (hardware B1.6) are not recommended, so these are a gamble now.
- **Parts:** Inkbird IBS-TH2, NZ$18–24 (a cold-resistant one for freezers about NZ$23); Shelly BLU H&T, about NZ$45; Xiaomi Mijia 2, NZ$12–16 each in packs. Coin cells or AAA; a year or so each.
- **Bonus:** whichever thermometer is loudest tells Pebble roughly which room it is in, which helps when it's lost (pebble-nav's call).
- **Effort:** S–M: the Bluetooth listener plus a parser and a part card per sensor family.
- **Limits:** a freezer's metal box weakens radio, and coin cells suffer at −18 °C (lithium AAA cells cope better). Anyone near the house can read these broadcasts. Temperatures are low risk; presence and door sensors should use BTHome's encryption.
- **Builds on:** everyday-uses 1b (maps), 2c (weather), 2e (plants); the workbench device home.

### B2. Key tags that beep
- **What you get:** "Pebble, find my keys." The tag on the keys beeps, Pebble listens and drives towards it, and says "In the couch, I think, by the left cushion." The same for the TV remote, a wallet or a school bag.
- **How:** cheap "iTag" tags (NZ$2–5) broadcast all the time and carry Bluetooth's standard "immediate alert": writing 1 makes them beep. Signal strength and hearing (plus A16) home in. Their button can also be a "come here" button, but only while connected, which costs battery.
- **Not usable:** AirTags and Find Hub tags work through online networks.
- **Effort:** M (homing needs nav; beeping alone is S).
- **Limits:** clones differ (some only blink, some beep when they lose the phone); signal strength jumps around; a tag in a closed drawer is muffled; coin cells last months.
- **Builds on:** things memory and "where is", which find only what was seen.

### B3. Thermal camera backpack
- **What you get:**
  - Draughts and cold spots: under doors, round window frames, where insulation is missing.
  - A map of surfaces at mould risk: surface temperature plus the room's dew point gives the humidity right at the wall (A10). For example, a corner at 15 °C in a room with a 13 °C dew point sits near 90 %.
  - "The heater's on in the empty spare room." "The oven door is hot and nobody's in the kitchen" (A2).
  - "That power board on the floor is much hotter than usual." A hint to check it, never a diagnosis.
  - Someone lying on the floor in the dark, to back up the existing check at night.
- **Part:** MLX90640, 32 × 24 heat pixels, 110° (BAA) or 55° (BAB), I²C address 0x33, 3.3 V, about 23 mA. NZ$48–68 on AliExpress. (The 16 × 12 MLX90641 costs more, about US$45 from Waveshare.)
- **Where it goes:**
  - Not on the body's ESP32. It has no free pins. Its 400 kHz bus carries the drop and front sensors, and a thermal frame takes tens of milliseconds to read, which breaks the firmware's rule that no step waits.
  - Instead, a **backpack**: an ESP32-C3 SuperMini (NZ$3–6) on the 5 V rail, with its own bus. It sends raw frames to the phone over Bluetooth or Wi-Fi, and the phone does the maths in numpy.
  - Best on the tilting head beside the phone, so it can sweep a wall from floor to ceiling corner, if `cad/check.py` finds room and the servo's margin holds (it runs at about 30 % of stall today). Otherwise on the front face above the bumper. Either way it needs an open hole: plastic blocks heat light.
  - Pebble can build and flash the backpack itself (workbench), so the owner's body firmware stays untouched.
- **Power:** under 0.1 A average from the 3 A rail, which also charges the phone. Measure.
- **Effort:** L (CAD, the backpack, the maths, the maps).
- **Limits:** shiny metal (pans, stainless steel, foil) reads wrong. Accuracy is about ±1–2 °C. It is coarse: at 3 m one pixel covers about 15–20 cm. **It is not a fire alarm. It never takes anyone's temperature:** no fever checks, ever.
- **Privacy:** shapes, no faces. Keep only derived numbers (surface temperatures on the map), never frames of people.
- **Builds on:** 1b, A2, A10, someone on the floor.

### B4. The dock as a hub
- **What you get:**
  - "The lounge got stuffy: 1,600 ppm of CO₂ with the doors shut." For context: NZ's Ministry of Education treats under 800 ppm as a sign of very good classroom ventilation. Pebble credits the figure and doesn't set its own target.
  - "Nobody's in the lounge," without a camera.
  - The dock tells Pebble the power went off even when Pebble is in another room.
  - Optional PM2.5: smoke in the air from the wood burner, candles or burnt toast. A hint, never an alarm.
- **Parts:** ESP32-C3 SuperMini NZ$3–6; SCD41 CO₂ sensor NZ$22–35 (I²C 0x62; about 15 mA average with short peaks near 200 mA; some cheap modules are fakes, so buy from a seller with reviews); LD2410C radar NZ$5–9 (about 80 mA at 5 V); PMS5003 NZ$20–30 (a fan, about 100 mA at 5 V).
- **Power:** the dock's own 5 V supply; nothing on the robot.
- **Effort:** M. Pebble builds it with the device kit.
- **Limits:** **CO₂ is not carbon monoxide.** The dock sits at floor level. The radar sees through thin walls and sees Pebble itself coming and going.
- **Builds on:** workbench (device kit, device home), 1b, the dock.

### B5. Leak probes
- **What you get:** "Water under the washing machine!", loudly, plus a notice if notices are on, before it ruins the floor.
- **Parts:** an ESP32-C3 asleep, two probes on the floor and 2 × AA, about NZ$8–12 a spot. It wakes when water bridges the probes and broadcasts at once (B1's listener hears it). Months to years on batteries. Ready-made Zigbee leak sensors (NZ$6–10) come with C1.
- **Where:** under the washing machine, dishwasher and hot water cylinder, and the sinks.
- **Effort:** S–M with the device kit.
- **Limits:** only where a probe is; batteries; radio from inside cupboards.
- **Builds on:** device kit, 1e. A new notice kind, "water leak", never held back in quiet hours.

### B6. Room presence radar
- **What you get:** "Is anyone in the spare room?" "The heater's on and nobody's been in there for two hours." For someone living alone, a camera-free hint: "movement in the bedroom this morning".
- **How:** the LD2410C has Bluetooth, and Home Assistant's `ld2410_ble` integration shows it can be read that way. So it needs only a USB plug, no ESP32. NZ$5–9.
- **Limits:** it ships with a default Bluetooth password, so anyone nearby could connect; pets and curtains move it; walls leak. **It is not a fall alarm.**
- **Builds on:** everyday-uses 3e and 1e.

### B7. "I'm OK" and "come here" buttons
- **What you get:** for someone living alone, one press says "I'm OK" and answers the daily check-in (3e). A long press calls Pebble.
- **Parts:** Shelly BLU Button Tough (BTHome), NZ$18–33. An iTag's button works too, at a battery cost.
- **Limits:** **not a panic button or medical alert.** Pebble never calls emergency services. A fall where the button is out of reach is missed.
- **Builds on:** everyday-uses 3e.

### B8. Mobile IR remote
- **What you get:** Pebble works the TV, heat pump or fan in whatever room it's in, instead of one fixed gadget per room. "Everyone's gone to bed and the TV's still on." It offers to switch it off.
- **Parts:** an IR LED and a receiver module, NZ$2–4, on the backpack's ESP32 (B3).
- **Rules:** the heat pump counts as a heater, so the owner approves it per device, as in 2a.
- **Limits:** aiming from 15 cm off the floor at a unit 2 m up a wall; heat pumps' long codes (the ESP32's RMT hardware sends them).
- **Builds on:** everyday-uses 2a; this replaces the fixed gadget.

### B9. Pebble's voice and alarm ears in far rooms
- **Voice pod:** an ESP32-S3, a MAX98357A amplifier (NZ$2–6), a small speaker and a USB plug. "Dinner's ready" is said in the bedroom without driving there, and alarms are repeated there too. Only "say it out loud" messages and alarms use it; private messages still find the person (1a).
- **Alarm ear:** the same plus an INMP441 microphone (NZ$2–7). It runs the beep-pattern match on the gadget and reports only "smoke-alarm pattern heard", never sound.
- **A first step for free:** a Bluetooth speaker the house already has. Many switch themselves off when idle, so not for alarms.
- **Effort:** L (streaming audio; the on-gadget detector needs the later C++ path).
- **Privacy:** a microphone in a bedroom is a big step, even one that only matches beeps. Owner decision below.
- **Builds on:** 1a, hearing.

### B10. Meat thermometer
- **What you get:** "The roast is at 63 °C." Pebble comes to tell the cook when the probe reaches the temperature they set.
- **Parts:** a Bluetooth probe whose broadcasts are known; `inkbird-ble` reads the iBBQ family and some Inkbird models. Inkbird's IBT-2X is about NZ$53. Check the exact model is readable before buying.
- **Limits:** the target is the cook's choice; Pebble shows what they set.
- **Builds on:** everyday-uses 3d.

### B11. Notes that stay up
- **E-ink board:** an ESP32 and a 2.9" e-paper screen (NZ$11–14) on the fridge: the list, today's reminders, bins night, the outside temperature. No burn-in, almost no power.
- **Battery-free labels:** NFC e-paper cards (NZ$24–57) that the phone writes when the card is held to it: "Bolognese, 19 October" for the freezer, a child's chore card. Fun, but on this body the card must reach the back of Pebble's head.
- **Builds on:** A3, workbench, case maker (4a).

## C. Later

### C1. Zigbee through a Pi that Pebble sets up
- Zigbee sensors are the cheapest door, leak, motion and button sensors (NZ$6–12 each), and they work locally with Zigbee2MQTT (GPL-3.0, fine because Pebble is never sold).
- **Recommended route:** a Pi Zero 2 W with a Sonoff Zigbee USB dongle (NZ$18–23), set up by Pebble's workbench (SD imager, SSH, offline packages), reporting to Pebble's device home. The other route, an ESP32-C6 or H2 as the coordinator, is less mature.
- Waits for the workbench's Pi path and an offline Node.js package.

### C2. UWB anchors in the dock
- A Qorvo DWM3001CDK in the dock (about €25 before VAT at DigiKey, often on long lead times) would give the distance to the dock to about 10 cm, in the dark, from anywhere in range. Two or three anchors would fix Pebble's position.
- **Against:** Android's UWB library is still a preview. A Pixel 8 Pro owner reported ranging working only one way round. On Pebble's sideways mount the Pixel 6 Pro's single angle points up and down, so the dock gives distance only. The AprilTag and charger-by-sight docking already work.

### C3. A microphone-array gadget
Only if A16 finds the phone can't give two raw channels.

### C4. Power-metering smart plugs
"The dehumidifier used 4 kWh this week" is useful. Switching a heater makes the plug a limb that could hurt: owner approval per device. Bought, certified plugs only; never one that has to be opened to flash it.

### C5. A door camera
"A parcel's on the doorstep" needs a camera that films the street and every visitor. Too heavy on privacy for now.

### C6. Wi-Fi ranging to ESP32 gadgets
The ESP32-S3 can answer Wi-Fi timing requests, but reports show errors of metres. Not worth building.

### C7. A real carbon monoxide sensor: recommended no
- An electrochemical cell (Winsen ZE07-CO, NZ$5–35) gives a CO number. The cheapest are likely fakes.
- Pebble on a shelf of hints would still invite false comfort: "Pebble said the CO was fine."
- **Instead:** if the house has a gas appliance, a wood burner or an attached garage, Pebble suggests a certified CO alarm once, and listens for its pattern, as it already does. Pebble is not a CO alarm.

### C8. NFC tags in each head mount
A sticker on each body's yoke, right behind the phone's NFC coil, would tell the phone which body it's in before any link comes up. A cheap alternative to the ID chip in `new-bodies.md` section 1, for when there are several bodies.

### C9. Tide tables
For coastal households: LINZ publishes yearly tide predictions, which the owner could drop into the inbox once a year.

## What Pebble can set up for people (offline)

Each of these is a device-kit config plus part cards (`plans/workbench.md`, sections 1–3). Pebble flashes it, tests it and keeps its profile in `mine/bodies/`.

| Gadget | Parts | How it talks to Pebble | What Pebble then does |
| --- | --- | --- | --- |
| Backpack | ESP32-C3, MLX90640, IR LED and receiver | Bluetooth or Wi-Fi | Thermal maps (B3), mobile remote (B8) |
| Smart dock | ESP32-C3, SCD41, LD2410C, PMS5003 optional | Wi-Fi to the device home | CO₂, presence, power cuts (B4) |
| Leak probe | ESP32-C3, two probes, 2 × AA | A short broadcast on waking | Leak notices (B5) |
| Freezer probe | ESP32-C3, a waterproof DS18B20 on a lead through the door seal, 2 × AA | A short broadcast | Freezer notices, where a Bluetooth thermometer can't reach out (B1) |
| Voice pod, alarm ear | ESP32-S3, MAX98357A, speaker, INMP441 | Wi-Fi | Far-room voice and alarm patterns (B9) |
| E-ink board | ESP32, 2.9" e-paper | Wi-Fi | The list and reminders (B11) |
| Button panel | ESP32-C3, two big buttons, 2 × AA | A short broadcast | "I'm OK", "come here" (B7) |

**How it stays safe:**
- **Only on the owner's say-so.** It works only on devices the owner points it at, after a brief and an explicit go (workbench, "Briefing before building").
- **Backups first.** It reads the full flash before writing and keeps every version, with the owner's original never deleted.
- **Never mains.** Pebble never designs, wires, flashes, checks or opens anything connected to mains, including a smart plug it would have to open to flash. Gadgets are USB- or battery-powered; mains devices are only bought, certified ones.
- **Batteries:** AA or AAA, lithium for cold places; 18650s only with protection; no bare LiPo in damp places or within children's reach.
- **Limbs that could hurt** (heaters, the heat pump, locks, pumps, plugs) need the owner's approval per device and go through the gatekeeper and law 1, as today.
- **Battery gadgets broadcast instead of joining Wi-Fi.** A short BTHome-style broadcast on waking costs a fraction of a Wi-Fi join, so batteries last many times longer. This is a new transport for the device kit.
- **Encryption and keys.** Presence, door and leak data say when the house is empty, so those gadgets encrypt (BTHome supports it). The device home needs a key per device before any gadget may act as a limb; today the body link accepts anyone (`NOTES.md`, "Still unverified").
- **Children's projects** stay low voltage, and cases follow the existing rules (PLA indoors, PETG or ASA outside).
- **Each gadget gets a privacy line** on its profile: what it senses, who can see it, how long readings are kept (storage plan: full detail 30 days, then thinned).

## Honest limits for all of it
- **Pebble is not a smoke alarm, a CO alarm, a medical device, a security system or a child monitor.** Every idea above that comes close says so in its own words when it speaks: the cooking watch, the alarm finder and test, the quake round, captions, the buttons, the radar and the thermal camera.
- **Health:** reminders and logs of what people told it, never advice, doses or diagnoses. No body temperatures, no cough or snore counting, no sleep tracking. YAMNet can score Cough and Snoring; these are deliberately left unused.
- **Privacy:** no sound is ever kept, only event names and times. Pictures stay dropped after a question, as today. Thermal frames and radar tracks become numbers on a map, never images of people. Visitors mode (A14) covers guests. Other adults' movements are not reported to anyone.
- **The laws** (`brain/pebble/laws.py`): law 1's speed and gap caps hold in every game and search; law 2 keeps private lines private and keeps every "it's safe" claim out of Pebble's mouth; law 3's heat limits cap the torch and the game rates.
- **Offline:** nothing here needs the internet. Weather comes only from the barometer and Pebble's own sensors. The only thing that leaves the house is the existing opt-in notice in words; without it, Pebble tells people when they come home.
- **The ladder:** everything in section A reads numbers the phone already makes, except the games (body points at a game rate, only during a game) and A16 (one small transform every 30 ms). Section B's processing happens mostly on the gadgets or in a few lines of numpy.
- **Speed:** at 0.25–0.3 m/s, "comes to tell you" takes a minute or more across a house. Urgent things go by voice where Pebble is, by the notice, or by a voice pod (B9).

## Decisions for the owner
1. **Where in the work order?** *Recommended:* a "household pack" (A1, A3, A4, A5's detector, A6, A7, A9, A10, A12, A14) right after Android round 3, because none of it drives or touches the self's freedoms. Anything that drives (A5's finder, A8's round, A13's hide and seek, B2's homing) waits for the nav fixes.
2. **Door knocks at night.** *Recommended:* noted quietly; repeated knocking (three times in two minutes) told at once to the owner or the inner circle. Pebble never opens the door.
3. **Unattended cooking reminder on by default?** *Recommended:* yes, once per cooking session, after 5 minutes with cooking still heard or seen and nobody in the kitchen.
4. **Lists: who may add and read?** *Recommended:* everyone in the household, children included, may add and read; strangers neither.
5. **"While you were out": whose comings and goings?** *Recommended:* only the house, pets, the door and the listener's own things. Children's arrivals to their parents only if the owner turns it on. Never one adult's to another.
6. **Captions and visitors mode.** *Recommended:* captions only when the person who asked is there. Pebble offers visitors mode when it sees three or more people it doesn't know; trusted people switch it on and off.
7. **Is the house in a tsunami zone?** *Recommended:* asked once at setup; the "long or strong" line stays off until the owner says yes.
8. **Which Bluetooth sensors to standardise on?** *Recommended:* Inkbird IBS-TH2 for temperatures (cheap, read from broadcasts, documented) and Shelly BLU for buttons and doors. Skip new Xiaomi units.
9. **Buy the thermal camera, and where does it go?** *Recommended:* yes, an MLX90640 at 110°, on a backpack board with its own chip, on the head if the CAD check passes. The body firmware stays as it is.
10. **A carbon monoxide sensor?** *Recommended:* no. Pebble suggests a certified CO alarm where there is gas, a wood burner or an attached garage, and listens for it.
11. **A microphone in another room (B9's alarm ear)?** *Recommended:* only the beep-matching ear, only where the owner places one, and never a stream of sound.
12. **Games without a grown-up home?** *Recommended:* the turn-on-the-spot games yes; hide and seek only with a trusted grown-up home.
13. **Zigbee route, when it comes.** *Recommended:* a Pi Zero 2 W, a Sonoff dongle and Zigbee2MQTT set up by Pebble, rather than an ESP32 coordinator.

## Suggested build order
1. The sharp layer on the face, and the Bluetooth listener in the Android app. Both are shared by many ideas.
2. A1 sounds that matter, A4 teach a sound, A2 the cooking watch.
3. A3 lists, A14 visitors mode and the guest card, A6 sound to sight and captions.
4. A5 the chirp detector and the alarm test, A9 the calendar and almanac, A10 the condensation line, A7 the torch.
5. B1 thermometers and B7 buttons (buy a few), then B2 key tags.
6. A11, A12, A15, A17, A18.
7. After the nav fixes: A5's finder, A8's round, B2's homing, A13's hide and seek; A16 if the phone gives two channels.
8. Gadgets Pebble builds: B5 leak probes, B4 the smart dock, B3 the thermal backpack with B8's IR, B11 the e-ink board.
9. Later: B9, then section C as the owner chooses.

## Tests to write with them
- **Sounds:** each notice fires on clear-licence recordings and stays quiet on 30 minutes of made-up household noise, as the alarm tests do; a knock in quiet hours is only noted; ggwave never triggers a knock or an appliance notice.
- **Taught sounds:** two examples are enough; a different tune doesn't match; forgetting a sound deletes its numbers.
- **Cooking watch:** one mention per session; the ladder takes over on smoke; the words never say "safe".
- **Alarm test mode:** a real alarm lasting over 30 seconds during a test still runs the full ladder; test mode ends by itself after 10 minutes; a stranger can't start it.
- **Lists:** a stranger can't add or read; every add is read back; the board leaves the screen after its time.
- **Captions and "while you were out":** nothing said before someone arrived is shown to them; no adult's movements reach another adult.
- **Games:** no wheel movement in the turn games; the crawling-child crawl holds in hide and seek; the child tier gates every game.
- **Bluetooth:** each parser reads recorded broadcasts from each supported sensor family; an encrypted broadcast with the wrong key is ignored.

## Sources
- Pixel 6 Pro hardware (sensors, spectral and flicker sensor, UWB, NFC, 3 microphones, camera fields of view): [Google Pixel hardware tech specs](https://support.google.com/pixelphone/answer/7158570)
- Pixel 6 Pro audio (three microphones): [DXOMARK Pixel 6 Pro audio test](https://www.dxomark.com/google-pixel-6-pro-audio-review)
- UWB on Android (supported devices, no background ranging on the Pixel 6 Pro, FiRa peers): [Android developers: UWB](https://developer.android.com/develop/connectivity/uwb); Pixel 6 Pro capability log (azimuth yes, elevation no): [Qorvo forum](https://forum.qorvo.com/t/ranging-pixel-6-pro-androidx-uwb-to-dwm3000evb/12347); one-way ranging with a Pixel 8 Pro: [Qorvo forum](https://forum.qorvo.com/t/dwm3001cdk-and-google-pixel-8-pro-ranging-only-works-one-way/18083); [DWM3001CDK at DigiKey NZ](https://www.digikey.co.nz/en/products/detail/qorvo/DWM3001CDK/24367348); [Qorvo DWM3001CDK](https://www.qorvo.com/products/p/DWM3001CDK)
- Wi-Fi ranging: [ESP-IDF FTM example](https://github.com/espressif/esp-idf/blob/dc859c1e67e/examples/wifi/ftm/README.md); [FTM/RTT limitations (MIT)](https://people.csail.mit.edu/bkph/ftmrtt_issues)
- Torch behaviour: [Android CameraManager.TorchCallback](https://developer.android.com/reference/android/hardware/camera2/CameraManager.TorchCallback)
- YAMNet's sound names: the class map shipped in this repo, `brain/pebble/hearing/models/yamnet_class_map.csv`; its embeddings output: `tools/export_yamnet.py`
- Smoke alarm chirps: [First Alert: why is my smoke alarm chirping](https://www.firstalertstore.com/store/product-support/why-is-my-smoke-alarm-chirping-beep-patterns.htm); [Vesternet: which alarm has a low battery](https://www.vesternet.com/a/answers/6696384/How-to-tell-which-smoke-alarm-has-a-low-battery)
- Fire and Emergency NZ (monthly tests, unattended cooking, one in four fires in the kitchen): [Paeroa fire, February 2026](https://www.valleyprofile.co.nz/2026/02/12/paeroa-home-destroyed-by-fire/); [Keep looking while you're cooking](https://fireandemergency.nz/news-and-media/keep-looking-while-youre-cooking-3/); [Importance of smoke alarms](https://fireandemergency.nz/incidents-and-news/news-and-media/importance-of-smoke-alarms-highlighted-again)
- Tsunami advice: [Get Ready: tsunami](https://getready.govt.nz/emergency/tsunami); [Long or strong, get gone factsheet](https://getready.govt.nz/assets/Uploads/documents/alternate-formats/large-print/pdf/09-long-strong-factsheet-lp-en-sep22.pdf)
- Stored water: [Get Ready: storing water](https://getready.govt.nz/prepared/household/supplies/storing-water)
- Matariki dates in law to 2052: [Te Kāhui o Matariki Public Holiday Act 2022](https://www.legislation.govt.nz/act/public/2022/14/en/latest/); [MBIE: Matariki public holiday](https://www.mbie.govt.nz/business-and-employment/employment-and-skills/employment-legislation-reviews/matariki/matariki-public-holiday/)
- Curtains before dark (EECA): [The Warehouse and EECA, The Warm House](https://www.thewarehouse.co.nz/thewarmhouse)
- 18 °C indoors: [WHO Housing and health guidelines, 2018](https://www.ncbi.nlm.nih.gov/books/NBK535294/)
- Mould at 80 % surface humidity: [AIVC paper](https://www.aivc.org/sites/default/files/airbase_4313.pdf); [Mumovic et al., UCL](https://discovery-pp.ucl.ac.uk/id/eprint/149446/1/BUILDING_SERV_ENG_RES_TECHNOL-2006-Mumovic-219-33.pdf)
- CO₂ in NZ classrooms: [Public Health Communication Centre](https://www.phcc.org.nz/node/908); [1News, 2021](https://www.1news.co.nz/2021/10/23/niwa-working-with-education-ministry-to-monitor-co2-in-classrooms/)
- BTHome: [BTHome format in Kaitai Struct](https://github.com/koenvervloesem/BTHome-Kaitai-Struct); [LWN on BTHome](https://lwn.net/Articles/925125); [Shelly BLE docs](https://shelly-api-docs.shelly.cloud/docs-ble/)
- Xiaomi custom firmware and its B1.6 warning: [pvvx ATC_MiThermometer](https://github.com/pvvx/ATC_MiThermometer)
- Inkbird broadcasts: [inkbird-ble supported devices](https://inkbird-ble.readthedocs.io/en/latest/supported_devices.html)
- iTag beeping: [micropython-aioble-itag](https://github.com/mcauser/micropython-aioble-itag); [RevSpace AntiLost](https://www.revspace.nl/AntiLost); [Espressif: Immediate Alert Service](https://docs.espressif.com/projects/esp-iot-solution/en/latest/bluetooth/ble_ias.html)
- LD2410 over Bluetooth: [Home Assistant ld2410_ble](https://www.home-assistant.io/integrations/ld2410_ble/); [HLK-LD2410C protocol](https://www.sudo.is/docs/esphome/components/ld2410/HLK-LD2410C_Serial_communication_protocol_v1.00.pdf)
- MLX90641 price: [Waveshare MLX90641](https://www.waveshare.com/product/modules/sensors/mlx90641-d55-thermal-camera.htm)
- Shelly BLU H&T in Europe: [The Pi Hut](https://thepihut.com/products/shelly-blu-h-t)
- AliExpress prices (NZ$, before GST, 19 October 2026): searches for [MLX90640](https://www.aliexpress.com/w/wholesale-MLX90640.html), [SCD41](https://www.aliexpress.com/w/wholesale-SCD41-CO2-sensor.html), [LD2410C](https://www.aliexpress.com/w/wholesale-HLK-LD2410C.html), [PMS5003](https://www.aliexpress.com/w/wholesale-PMS5003.html), [SPS30](https://www.aliexpress.com/w/wholesale-SPS30-sensirion.html), [Mijia thermometers](https://www.aliexpress.com/w/wholesale-LYWSD03MMC.html), [Inkbird IBS-TH2](https://www.aliexpress.com/w/wholesale-inkbird-ibs-th2.html), [Shelly BLU H&T](https://www.aliexpress.com/w/wholesale-shelly-blu-h%26t.html), [Shelly BLU Button](https://www.aliexpress.com/w/wholesale-shelly-blu-button.html), [key finders](https://www.aliexpress.com/w/wholesale-itag-bluetooth-key-finder.html), [ESP32-C3 SuperMini](https://www.aliexpress.com/w/wholesale-ESP32-C3-SuperMini.html), [Zigbee leak sensors](https://www.aliexpress.com/w/wholesale-zigbee-water-leak-sensor.html), [Zigbee dongles](https://www.aliexpress.com/w/wholesale-zigbee-3.0-usb-dongle-coordinator.html), [INMP441](https://www.aliexpress.com/w/wholesale-INMP441.html), [MAX98357A](https://www.aliexpress.com/w/wholesale-MAX98357A-I2S-amplifier.html), [IR modules](https://www.aliexpress.com/w/wholesale-38khz-infrared-receiver-transmitter-module.html), [2.9" e-paper](https://www.aliexpress.com/w/wholesale-2.9-inch-e-paper-module.html), [ZE07-CO](https://www.aliexpress.com/w/wholesale-ZE07-CO-sensor.html), [Bluetooth meat thermometers](https://www.aliexpress.com/w/wholesale-ibbq-bluetooth-meat-thermometer.html)
