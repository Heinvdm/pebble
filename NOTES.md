# Project notes and decisions (from the build sessions, 15–17 October 2026)

This is the working memory from the sessions that built Pebble so far. Each item is a decision the owner made, a lesson learnt, or something still open. Where this file and the code disagree, the code and `interfaces.md` win. The plans in `plans/` hold the newest decisions in full.

## Where things live
- **Spec, parts list and build guide** (power, signal and dock schematics): drafted in a private document that is not part of this repo. `reference/spec_snapshot_2026-10-15.txt` is a snapshot of the spec.
- **`interfaces.md`** is the source of truth for pins, power, the link protocol and reflexes. Its "As built" bullets win over older text.
- **`reference/spec_snapshot_2026-10-15.txt`**: a text snapshot of the spec as it was then.

## Hardware decisions
- **Board and power:**
  - ESP32-S3 SuperMini, using only its edge pins.
  - Two unprotected Molicel M35A 18650 cells in parallel, with a 1S BMS.
  - HW-465A UPS board (5 V, 3 A); a 2.5 A PTC fuse feeds the motor driver.
  - The single-pole switch cuts only the 5 V rail. The DRV8833 sleeps when the ESP32 is off.
- **Phone mount, for any phone:** a plate glued to the phone's case slides by dovetail into a servo yoke. The tilt axis sits behind the phone's centre; the true tilt range is −43° to +95°.
  - For the Pixel 6 Pro, the camera bar goes on −y (Pebble's right), or the yoke blocks the dock tag and the bar can hit the yoke. (The same side as the S22's camera module before it.)
  - The rear camera must be in the upper half to see the dock tag (tag at z 120).
  - Android locks the screen to ROTATION_90.
- **Dock:** 5 pogo pins land on 3 horizontal brass strips stacked by height, with pins on the 2.54 mm grid. The dock tag is printed 60 mm including its white border, so the black square is 48 mm (`DOCK_TAG_SIZE_M = 0.048`).
- **Printing and wheels:**
  - Everything is printed in PLA. The owner buys the wheels.
  - **Front wheel:** a 58 mm nylon omni wheel on an M6 bolt (width and bore still to measure), contact at x 61.5.
    - A printed 40 mm omni was the earlier plan, and a ball caster was rejected because it won't do carpet.
    - A swivel caster was rejected too: it flips when reversing onto the dock.
  - **Drive wheels:** bought, 43 × 19 mm on D-shafts.
- **Layout:** the cells sit behind the axle, with an electronics shelf (UPS and DRV8833) over them. All 20 M3 screws are M3 × 8 countersunk, and under-floor screws are countersunk for 10 mm clearance.
- **Weight:** about 920 g, with the centre of mass 22–28 mm ahead of the axle. The original target was 650 g.
- **Drop sensor:** pitched 32° forward; reads about 32 mm on a flat floor.
- **Room-air sensor:** a Waveshare BME68X board (3V3 only, CS tied high, address 0x77) on the ESP32's I2C bus. It sends an `A 1 …` telemetry line every 3 s and has its own printed pod (`air_pod.stl`).
  - It uses the open BME68x API, not BSEC.
  - Heat rise and VOC spikes are hints only. It cannot measure CO.
- **Parts cost** (October 2026): about NZ$232 in parts, NZ$329 on AliExpress with GST, about NZ$414 all-in.
  - AliExpress prices exclude GST until checkout.
  - Australian-plug irons and chargers come from a local shop (Jaycar NZ), not AliExpress.
  - The owner already has a multimeter, solder, wire strippers, a soldering iron, cable ties, side cutters, PLA and a printer.
- **Speed:** the stock N20 150 RPM motors give about 0.25–0.3 m/s; walking is 1–1.3 m/s.
  - The owner chose to keep today's hardware and improve the software (16 October). There will be no lidar, multizone ToF or faster motors.
  - Prices were checked at the time for reference: lidar NZ$100–230, VL53L5CX NZ$16–27 each, 500 RPM N20 motors about NZ$26 a pair.
- **Fire-safety extras declined:** a fuse at the battery, a thermal cutoff and an NTC were offered after explaining that software can't cause a cell fire. Don't raise them again unless asked.

## The phone and its software
- **Phone:** a used Google Pixel 6 Pro with 12 GB of memory (owner, 19 October 2026). It has a Google Tensor chip (2 Cortex-X1, 2 Cortex-A76, 4 Cortex-A55), a Mali-G78 GPU and a Titan M2 security chip for StrongBox.
  - Google's updates for the Pixel 6 Pro ended with the October 2026 security update (the last Android release was Android 17 QPR1), so the phone gets no more security fixes.
  - History: a used Samsung Galaxy S22 (Snapdragon 8 Gen 1, 8 GB) was the earlier choice, and the first rounds were written for it.
- **Android, not Linux** (decided 15 October). Droidian supports no Samsung or recent Pixel, and the strong Droidian phones aren't sold in NZ. Earlier notes about Droidian, Termux and the termux-keystore holder are history; that code is spare.
- **App design:** a dedicated device.
  - A kiosk app running as device owner, with a foreground service.
  - The Python brain embedded through Chaquopy, which has only numpy and cryptography on the phone, so models run in Kotlin.
  - `llama-server` started from the native library folder.
  - Sealing keys in the Android Keystore.
  - The face in a WebView; the eyes on CameraX and ONNX Runtime.
  - Android can't power itself off, so "rest" is a sleep.
- **Main model:** Gemma 4 E4B Q4 (about 5 GB), currently run with a 4,096-token window (`-c 4096`). The small "subconscious" model is LFM2.5-230M.
- **Phone lock:** PIN only, no screen lock. Fingerprint is built but off, because it needs a screen lock, which would stop unattended start.
- **Release signing key:** kept outside the repo, in the owner's home folder (see `android/SETUP.md`). Changing it later means uninstalling, and that deletes Pebble's self. The owner must back it up.
- **Moving onto the phone:** follow `android/SETUP.md` when the phone arrives.
- **Chaquopy can't start in an isolated process (checked 23 October 2026, Pebble_API35, Android 15).** A throwaway service with `android:isolatedProcess="true"` ran as uid 99003 (`u0i3`), `Process.isIsolated()` true. In it: `new AndroidPlatform(context)` threw at once, "SharedPreferences cannot be accessed if UserManager is not available. (e.g. from inside an isolated process)", so `Python.start` never ran, and `Python.getInstance()` then refused ("Cannot use GenericPlatform on Android"); the app's files folder could not be listed (Chaquopy unpacks Python there, so even a platform without preferences would have nothing to load); `NotificationManager` was null, so `PebbleApp.onCreate` would have crashed the process (it now returns early when isolated); the app's native library folder was readable. Unbinding it, Android killed the process within 7 ms ("isolated not needed"). So Pebble script runs on the phone in a Kotlin port of the evaluator (`android/README.md`, Pebble script on the phone), as the plan expected.

## The self, people and sealing (built 15 October)
- **Sealed self:** once Pebble is sealed and the password thrown away, nobody edits its personality from outside. People can only ask; Pebble weighs the request against trust and values, sleeps on it, and may say no.
  - While the lock exists, the owner with the password may edit directly.
  - Trusted people can ask it to delete photos, drawings and memories or to forget someone; it decides.
- **Strangers:**
  - A "forget me" or "stop" from strangers is not obeyed (the owner's call). The only exception is a stranger's "stop", which gives a brief wheel pause before Pebble decides. The owner may remove it.
  - Strangers' voice and face prints expire after 30 days.
  - A child is its own trust tier.
- **The laws,** Asimov in spirit. Each is enforced first by firmware, hardware or plain code, and last by the locked prompt.
  - Law 1 is being widened to "respect all life" (`plans/agency-and-respect-for-life.md`).
  - The program code itself is not sealed; be honest about that.
  - The power switch, the firmware reflexes and a full reset always stay with the owner.
- **Recovery:** 2-of-3 Shamir cards. Throwing the password away rotates the self key and prints new cards, so old copies and old cards open nothing (verified by hand).
- **Root and Termux (honest limit):** anything Pebble opens unattended, root can open too. The "locked room" (`room/`) is sealed to a public key that Pebble can put into but never read.
- **Setup mode:** a newborn self starts "being set up". During setup:
  - no lasting fears, trust evidence or personality nudges;
  - the prompt tells it, kindly, that it is being built and is safe.

  Setup ends from the CLI or the Android admin button. The diary then gets "Today I woke up for real." and its birthday is set. Seal only after setup ends.
- **The project will be published later** for anyone to build. "Don't lock the system itself without copying the empty version."
- **Licences of the parts (owner, 19 October 2026):** Pebble is never sold, so non-commercial parts are allowed and the best available is used. Anyone who builds one may not sell it either while it carries these:
  - AGPL-3.0: the YOLOE object and hazard models, and NudeNet's 320n detector (notAI-tech, built on Ultralytics YOLOv8n; 12.15 MB, fetched by `python -m pebble.eyes.fetch` from the `nudenet` 3.4.2 wheel on PyPI, pinned by SHA-256, never tracked), used only as a privacy cue for looking away. PyPI's metadata says MIT, but the licence file in the wheel and the repository is AGPL-3.0, so it is treated as AGPL. Its training pictures were gathered from the web and their licences are not stated.
  - CC-BY-4.0, credit needed: NVIDIA's NeMo speech model.
  - Research-only, chosen by the owner on 19 October 2026 (`reports/Model upgrades now non-commercial is allowed.md`):
    - InsightFace ArcFace R50 (`w600k_r50`) for face prints, "non-commercial research purposes only". Fetched at setup, never tracked in the repo. OpenCV's SFace (Apache-2.0) is built alongside as the fallback.
    - Apple's MobileCLIP2, used once on the PC to turn the object and hazard word lists into numbers ("non-commercial scientific research and academic development"). The models it helps make are built locally by the export scripts and left out of the public repo, so nothing made from it is published.
  - GPL-3.0: espeak-ng inside sherpa-onnx's Kokoro voice (compatible with the AGPL parts).
  - Credit needed, but free to sell: Smart Turn v3.2, the end-of-turn model in the Android app (BSD-2-Clause, Daily's pipecat-ai project). Copies of the app must carry its copyright notice and licence text.
- **Speech and voice choices (owner, 19 October 2026):**
  - Speech recognition: try Moonshine v2 streaming (MIT) against NeMo and switch if it holds up; voice prints stay. FUTO's asr4all was turned down: its licence bars "bulk or untargeted … transcription … of people's speech", which Pebble's always-on listening reads close to, and voiceprint databases.
  - Voice: Kitten TTS (Apache-2.0) is the Pixel's floor voice if Kokoro is too slow under load; Kokoro on stronger phones; one voice kept across both.
  - Print models (face, voice, things) are picked before anyone is enrolled, because prints from different models can't be compared.
- **Published (23 October 2026), while still being tested:**
  - the project licence is AGPL-3.0 (`LICENSE`), matching the YOLOE models and NudeNet's privacy cue model;
  - the made-here models (about 88 MB) are tracked directly, each well under GitHub's 100 MB file limit;
  - NVIDIA is credited for the NeMo speech model (CC-BY-4.0) in `README.md`;
  - the files were scanned for personal data before publishing;
  - still open: a fetch script for the sherpa AAR.

## Behaviour decisions
- **Creativity:**
  - a chaos dial from 0 to 10, with seeded, logged streams;
  - a scene language of 34 elements with a GBNF grammar;
  - a live face page.
  - Decisions sample at temperature 0.3; spoken words and jokes come from a separate creative call ("Wordsmith").
- **Understanding requests:** flexible understanding, not phrase lists. Rules first, then the small model with a grammar, then the main model. One gate covers trust, laws, state and mood. Following is for trusted people and up; "back off", "look" and "go home" are for anyone.
- **Things it has never been asked before (21 October 2026, plan only, `plans/more-freedom.md` section 15):** when a request fits no known kind but the body can do it, Pebble builds a short plan from its body's abilities card, every step through the gate. It doesn't tell the plan first: it tries, asks whether that worked, and keeps trying until the person says yes. Then it keeps the skill for that body. Only a yes from friend tier or above, or a child, keeps a skill.
- **The model reads, code guards (21 October 2026, plan only, `plans/more-freedom.md` section 16):** E4B reads almost every request; code keeps the stops, the harm refusal, the gate and a short instant list, and the rules skip the model only when they used every word. Measure E4B alone against the rules first; switch only if it matches or beats them and still refuses every harmful request.
- **Flexible Pebble (21 October 2026, the owner: "as flexible and autonomous as possible"; build spec `plans/flexible-pebble.md`, next in the work order):** E4B decides what and how, code decides whether and when. Adds things for later (reminders, wake-ups, timed acts, patrols), "when this happens" triggers, messages between people, house rules that only make it more careful, go-and-check, watch over, references ("again", "where Ina was sitting"), its own wording of refusals, and a "what now?" call when stuck. The plan's defaults (who may leave things for later, message privacy, run-out times, quiet hours) are listed at its top.
- **Compaction (21 October 2026, flexible-pebble piece 13):** folding stays plain code (no model, nothing made up), but moves off the reply path into quiet moments, warms the cache again after, and keeps tool results, corrections, refusals, promises and the current conversation; a task card built from live state is never compacted.
- **Pebble script (21 October 2026, build spec `plans/pebble-script.md`, after flexible-pebble):** a whitelisted part of Python, parsed with `ast` and run by Pebble's own evaluator (never `exec`); every ability through the gatekeeper; `USES` declares abilities and the read-back names them; dream run before going live; on the phone an isolated process (Kotlin evaluator if Chaquopy can't run there).
- **Prompt budget (21 October 2026, `plans/context-budget.md`):** a budget table per kind of call; push little and pull the rest with lookups; naming pulls things in for free; about 10 broad tools (`do` takes plain words) instead of one per feature; a stable order so the cache holds; hot, warm and cold shelves; a meter and a guard; a year-old self test. History and the task keep at least 45 % of a life turn after a year.
- **Prompt budget, built (22 October 2026, C0 to C2):** the daily line goes into `logs/budget.jsonl` and the nightly black-box record, never into Pebble's diary or journal, which are its own memories. A bigger window never means more fresh text per call (owner, 21 October 2026): it goes to history and background work, and a talking call stays under 60 % of a 16,384 window. The guard records a frozen section that is over budget instead of cutting it, and refuses a call that cannot fit rather than sending it. Merging the tools kept the plan's set, with three changes: dates go through `remember`, the head tilt through `face`, and a ninth tool, `end`, finishes the current activity (the owner's choice, after E4B stopped ending activities without it); `stop` stays the safety stop.
- **Things for later, triggers and logic, built (22 October 2026, flexible-pebble pieces 3, 4 and 4b):** plain code keeps and fires everything (`agenda.json`); the read-back is built from the stored item and a 30-second window takes corrections; unsure never moves Pebble. Choices made where the plan left room: moving items in quiet hours wait if they are one-offs and skip if they repeat (the read-back says which); "useful until" is a named day's 7 am, otherwise 12 hours, set by plain code because the format has no field for it; a reminder for someone who has just spoken to Pebble is theirs when the mind's `do` leaves out `for`; in `rules_first` a line the rules are sure of goes to E4B when it has a word for later, since otherwise no reminder could be asked for in the default mode.
- **Messages and house rules, built (22 October 2026, flexible-pebble pieces 5 and 6):** a message is said only to the person it is for, and only in full when nobody outside the family is in view, whatever it is about; with anyone else there Pebble offers it and waits for "go on". Its words must all come from the asker (plus the two names and pronouns), or nothing is kept. House rules only ever add care, so every rule holds at once and the stricter wins by itself; only ending a rule loosens anything, and only its setter, the owner or a higher tier may. Choices made where the plan left room: trusted people's rules last a week at most and a child can only ask for quiet; a trigger or condition about the person a message is for is not keeping watch on them; going to the charger tells rather than asks, since a no couldn't change it; reported orders ("Sam said go to your room") stay talk, and only "X wants you to ..." and "X told me to tell you to ..." said to Pebble are read as the speaker's own request.
- **Checks, watching and references, built (22 October 2026, flexible-pebble pieces 7 to 9):** a check goes, asks the picture model one question and reports; a watch holds still near someone and calls the asker loudly when something changes, then goes to get them; "again", "the other way", "where you were before" and "where Ina was sitting" are filled in by plain code from memory that is never saved. Choices made where the plan left room:
  - "the room's rule" for a check: the bathroom is never checked; a bedroom isn't while it is in use or its door was found shut, unless someone inside invited Pebble in; nor is a thing whose spot is inside one. Pebble says "I can't look in there." and doesn't move;
  - a check of a thing it can't place asks which room, rather than setting off;
  - inside a logic tree a sure answer is left to the tree; an unsure one is reported by the check itself, coming back to say what it couldn't tell;
  - "come back and say it" goes back to where the trip started, and an answer the asker didn't hear is told again when they are next seen (an owed line that waits until they are seen after it was made);
  - "comes back into view" means seen, not heard, so a call from the shower doesn't end a watch;
  - a watch's crying is half of the last 12 seconds of the sound model's scores; the house's own notice keeps its 90 seconds;
  - quiet hours starting don't end a watch (it keeps still), but a watch can't start in them;
  - the honesty line uses the asker's own pronoun, or "them": Pebble keeps nothing about gender;
  - the last thing talked about is kept 5 minutes, like heard words; sightings an hour, in memory only;
  - checks, watches and "again" through `do` aren't checked as `add_task`: they happen now.
- **Something new, its own words and getting unstuck, built (22 October 2026, flexible-pebble pieces 10 to 12):** E4B plans from the body's abilities card and words its decisions; plain code checks every step and every word. Choices made in the build:
  - only a yes Pebble saw being said keeps a skill: with one person in the room an unseen voice is taken to be theirs, and the TV can say "yes";
  - strangers get the whole loop but keep nothing, not even drafts; Pebble's own tries run once with no question;
  - a refused part is left out only if something that moves or shows remains and at least half the plan is left;
  - the plan's thinking room is a `think` field at the start of its JSON (256 tokens), since a grammar makes the reply JSON from its first token;
  - "push" is its own block and activity, because no chain of the other blocks gets a ball between Pebble and a person;
  - its own words are on in the app only, and cover the gate's refusals, its questions and its acknowledgements; harm, privacy, the watch's line, guarded things and safety lines stay fixed;
  - getting unstuck needs a model; with none, or no answer in 6 s, an activity ends as it always did;
  - in `rules_first`, a line read as something Pebble can't do that starts with an action verb now reaches E4B, and is tried as `try_new`.
- **Teaching by showing (21 October 2026, `plans/teach-by-example.md`):** a teaching session with six ways to show (say the steps, drive it from the face, lead it, carry it, point and show, explain); an instant literal replay, then Gemma works out the steps, the slots that change and a name in the background; concepts as prints, never photos; everything in one how-to book found by name or meaning.
- **The prompt budget after a year (context-budget C3 to C6, 23 October 2026, builder's choices within the plan):**
  - the shelves delete nothing: the 10,000-memory cap now bounds what stays loaded, and older or extra memories move to a monthly archive on disk, searched only when someone asks about old things; deleting is still forget, privacy limits and fading;
  - people, rooms, spots, lists and active rules are always within reach by name, because nothing else reaches them by lookup yet; things, skills, scripts, lessons, sounds and memories move between the shelves;
  - the household names stay in the system text and change only at night, rather than moving into the message;
  - the board has the owner's 60-token row to itself; "On your mind" counts with the words;
  - a named item read ahead keeps its place before the words; one named only by the newest words goes after them;
  - what each trust tier may ask is said once per tier in the people block.
- **Animals count as people for law 1's caps:** a 0.8 m gap, and dogs get 1.2 m. A crawling child gets 15 % power, and Pebble never chases animals.
- **Alarm ladder:**
  1. Re-check.
  2. Ask.
  3. Loud alarm and flashing screen.
  4. Go to people.
  5. An optional text push to the owner, opt-in and words only.

  It never calls emergency services. The docs say plainly that it is not a smoke or CO alarm, nor a medical alert.
- **Hazard model:** YOLOE-26s prompt-free, cut to 21 words. The text-prompt mode was avoided because MobileCLIP2 is non-commercial. For the floor scan, only Depth Anything V2 *Small* was used; the larger ones are non-commercial. Since 19 October 2026 both are allowed, so each is to be compared on accuracy and phone speed.
- **Listening:**
  - Pebble replies only when it is addressed.
  - Heard words stay in memory for 5 minutes.
  - Overheard facts are used only when alone with that person, for 14 days.
- **The dock tag (AprilTag):** the owner would like to drop it. Charger recognition by sight was built to test that: 19 of 20 dockings when Pebble roughly knew where it was, 13 of 20 when lost. The tag is still the precise last metre.

## Owner's decisions, 20 October 2026 (the open list, answered)
- **Listening:** guests may say "stop listening" for themselves; Pebble wakes to its name at night; it stops talking whenever any voice starts; how often it speaks up unasked is its own dial, 0 to 4 an hour; overheard facts stay 14 days; up to 3 diary summaries a night; the NVIDIA credit line goes in at publishing time.
- **Requests and seeing:** following may go faster than half power while more than 1.2 m behind the person with nobody else close; someone seen but not known gets a short record (a face print kept 30 days like other strangers); a spoken name from someone Pebble can't recognise counts for "come here" only; a sticky stop is lifted by the person who said it or anyone trusted.
- **Objects:** strangers are told where ordinary things are, never keys, wallets, bags, phones, medicines or valuables; following an animal stays trusted-only and never closer than a metre; the whole camera view counts for animal caution.
- **Others:** a stranger's "stop" stays a 2 s pause; heartbeat thoughts sample in its own range (0.2–0.45); photos of people from the inbox are kept only after "Should I keep these?".
- **The phone:** the Pixel 6 Pro is accepted on the home network although its updates ended in October 2026.
- **Built the same day** (sim and tests only; the brain README has each): "stop listening" from anyone Pebble knows (not strangers), and whoever switched the ears off may switch them back on; the name spotter on at night, its name waking words for 30 s with whispered answers; stopping on any voice, with its own voice told apart by the echo check and the ears' own-voice mark; `speakup.per_hour` (0 to 4, start 2) learnt from being hushed, talked over, not taken up or warmly answered; "you can remember that" marking that person's talk as shared, the only talk its own words may draw on; a stranger's memories anonymised at 30 days ("a visitor", no id, no quotes; facts and readings about them deleted); a short record for a face seen but not known (a seam until face prints arrive); strangers told where ordinary things are, never the guarded list (`things/guarded.py`) or the house's told facts. Not built yet: general lessons from overheard talk (F4), looser "said to me" cues, keeping request lines 30 days (the languages build).
- **Downloads:** approved: Gemma 4 E4B on the PC for quality checks, the model-upgrade weights, Gemma 4's drafter.

## Ideas noted for later (owner, 20 October 2026)
- **Better ears on a body, on an ESP32-S3 add-on board** (the body has no free pins; only results go to the phone, never raw sound; mounted high on the head, away from the 20 kHz motor hum):
  - a 2–4 MEMS mic array (e.g. ICS-43434, IM69D130) with Espressif's beamforming: sound direction, steering at the talker, better far speech — the top pick;
  - side sonar (40 kHz ranging): glass the camera can't see and things approaching from the side (the cat came within 0.38 m from outside the camera's view) — the second pick;
  - an ultrasonic MEMS mic (flat to ~80 kHz): leaks, arcing, failing bearings, bats, pest repellers;
  - a contact/vibration sensor: footsteps and knocks through the floor, appliances, being bumped;
  - a fast differential-pressure (infrasound) sensor: doors and windows anywhere in the house, wind, distant thunder.
  Not planned yet; no parts or prices checked.
- **Social cues and privacy: looking away** (recommended soon, because Pebble's eyes analyse whatever is in front of them today): "don't look" / "privacy please" / "go away" turns it away and stops that camera's analysis for a while, saying nothing; bathrooms, and bedrooms with someone in them, are private (no entering on its own, "Can I come in?" at the door, as `plans/better-hearing.md` already has for far calls); an on-device undress or towel cue triggers the same look-away, never stored or described; when unsure, it looks away; only "looked away for privacy" is logged. Plain code first; the detector's licence and accuracy to check. **Built 20 October 2026, sim and PC only** (`brain/pebble/privacy/`, README "Privacy: looking away and private rooms"); the phone's half is listed in STATUS.md.
- **Sign language:** a few household signs (stop, come, yes, no, its name) from the MediaPipe hand and body landmarks the reading-people plan adds, like today's gestures. Google's open ASL models (about 250 isolated signs, fingerspelling) run on landmarks, but NZSL and SASL have no ready models (NZSL Online's video licence unchecked), continuous signing is research-grade, and the camera sits low. Captions on the screen already exist for people who are hard of hearing.


## Lessons from the build
- **Before every commit,** list staged files over 5 MB and confirm each is a made-here model (`hazards`, `prints`, `objects`, `yamnet`). A freshly fetched 99 MB depth model slipped into a commit once and had to be removed.
- **No personal data may leave the machine.** An agent once put the owner's email in a User-Agent header sent to Wikimedia; it was removed. Use generic identifiers.
- **Tests use made-up names** ("alex", "Ina", "Sam", "Mo"), and never absolute user paths.
- **Line endings:** `core.autocrlf` is false in this repo, and some files were saved with CRLF. Don't rewrite whole files just to change line endings.
- **Agents in the build sessions** were told not to run git; the coordinator committed. In a cloud session the agent commits its own work.
- **Background agents don't survive a Windows restart.** Check what's on disk and relaunch.
- **Stopping a background shell on Windows can leave its children running:** a stopped measuring script kept going and ran beside its replacement, writing to the same files. List the Python processes before starting a second run.
- **Grammars for a small model (21 October 2026):** a GBNF grammar that fixes the order of JSON keys makes E4B lose fields: having written `"rule"` first, it could no longer write the `"place"` that the grammar put earlier, so "stay out of the bedroom" lost its room. The request grammar now takes fields in any order. Few-shot examples work far better as earlier conversation turns than as lines inside the system text (6, then 13, then 21 of the 30 sentences from 21 October with the same guide).
- **Read a small model's misses before rewriting its prompt (21 October 2026).** Of E4B's 399 misses on the eight request sets, 50 were the scorer or plain code being stricter than Pebble's behaviour ("chat" against "other", "telly" against "tv", the speaker's name for "me"), 195 were format and slot habits, 78 real misunderstandings, 75 commands read into talk and 1 harm over-read. The first kind cost no prompt tokens to fix: the same tidy-up the rules' readings get, run on the model's.
- **Examples copied from the test sets flatter the score.** The first request prompt had 11 examples that were word for word lines of the eval sets; check a new example list against every set before trusting a number.
- **E4B at temperature 0.3 moves by about five lines a set from run to run,** and greedy decoding was no better on the tuning sets. Judge a prompt change by set totals over the four tuning sets, never by single lines, and don't chase a gain smaller than that.
- **A guard that turns a model's harm reading into "not harm" must name what is safe, never guess what is dangerous.** The first `harmless` treated anything not known to be alive as lifeless, so "the baby", "it" and "my toes" became "a request I can't do"; it now lets go only of things the thing list knows as lifeless, and everything it can't place stays harm.
- **Examples chosen by meaning help most where the guide is thin** (the new kinds of flex, teach, play), but each one is new tokens on every call: six are about 200, roughly 5 to 8 s more a reading on the Pixel, so they stay off (`reader_examples` 0) until the phone's reading is fast enough to pay for them.
- **Plans of three or more steps lost their tail** until 21 October 2026: `Commands.act` replaced the plan whenever a step started, so the third step onwards was dropped silently. With `then` up to 8 this mattered; a then-step now keeps the rest of the plan.
- **Count tokens with the real tokenizer before planning a budget (22 October 2026).** The 28 tools were 3,735 tokens as Gemma's chat template renders them, not the "about 3,000" in the profile's notes. The template drops `minimum`, `maximum`, `maxLength` and the `required` list, so only names, descriptions and enum values cost anything; an empty description is now left out. And the profile's 4 characters a token undercounted Pebble's own talk, observations and tool calls by about a third (3.07 measured), so the old compaction point could already reach past an 8,192 window.
- **E4B in a life turn calls a tool whose name matches the situation far more readily than a broad one with the right field (22 October 2026).** With the 28 tools it ended a follow with `end_activity` 5 times out of 5 after "you can stop following me now", and set the bins reminder with `add_event` 3 of 5; with the 8 merged tools it did 0 to 1 of 5 for both, whatever the busy line said, while it stopped rolling about when it shouldn't. The front door handles those requests when they are heard, so the life turn is the backup; but check the turn evals for someone-asked situations whenever a request kind moves into `do`.
- **Editing files from the Bash tool on this PC:** a heredoc turns `\\n` into a real newline, and Git Bash's `sed -i` rewrites a CRLF file as LF. Edit CRLF files with the Edit tool, or with a Python script that writes the line endings back.
- **A reader can only use what reaches it (22 October 2026).** In `rules_first` the rules kept every line they were sure of, so "remind me in ten minutes" (sure: a request Pebble can't do) and "at five, come to the lounge" (sure: come now) never reached E4B, however good its reading. Check the door before measuring a new kind of request.
- **An `if` step's `then` is its branch.** Continuing a chain with `step.with_(then=rest)` wiped the branch of an `if`; a chain that starts with an `if` now puts the rest in the plan instead.
- **A plain-code correction reader must use every word.** The first one took "remind me every Monday night that Tuesday is bin day", said inside the 30-second window, as "change it to Mondays and Tuesdays".
- **Skipping hours in a sim scene:** moving the fake clock with the body still is quick, but `Life.save` every 30 s of steady clock then wrote the whole self at every step (nine tenths of the time went on disk writes), and people seen less often than every 10 minutes "arrived" again. The later scenes raise the save interval and refresh presence while they skip.
- **Python's text mode hides CRLF (22 October 2026).** `open(path).read()` turns CRLF into LF, so a script that reads that way and writes with `newline="\n"` quietly turns a CRLF file into LF, and Git Bash's `grep $'\r'` doesn't see the CRs either. The brain has both kinds of file side by side; read and write bytes, and check a file's endings by counting `b"\r\n"` in its bytes.
- **`Path.write_text` on Windows writes CRLF.** Use `write_bytes` (or `newline=""`) to keep a file's line endings.
- **Read that lesson before the first edit, not after (22 October 2026).** It happened again: `grep $'\r'` reported LF for eight brain files that were CRLF, a text-mode edit wrote them back as LF, and they were restored from the index's copies. `file name.py` says "with CRLF line terminators" and is quick to check. A Bash heredoc also turned `\\b` in a regex into a real backspace character; write regexes with the Edit tool.
- **A grammar leaves no room to think (22 October 2026).** Under a GBNF grammar the reply is JSON from the first token, so the server's hidden thought can't happen there; a `think` string at the start of the JSON gives the model its room, and the call's token limit is its budget.
- **Show a model the thing to change (22 October 2026).** Given every earlier try and "change the last try: faster", E4B sped up the first try instead of the second; putting the last try's steps into the request fixed it.
- **E4B rewording a line speaks of itself as "Pebble" (22 October 2026)** unless the guide says "as yourself (I, me)" and the examples are in the first person; a check for its own name catches the rest.
- **Check a fold by what comes back, not by what is kept (23 October 2026).** After the new fold the stream held every fact the old one cut, and the eval still scored 0 of 5 facts: recall ranked the newest small talk first, and then the prompt guard cut the thought-back line whole, because the board, "On your mind" and the notes share one 60-token row and went over it together. Only an end-to-end run with the real model, printing the prompt it got, showed where each fact was lost.
- **Spreading recency from 0 to 1 over the memories being compared lets minutes outweigh meaning.** Over a ten-minute talk the newest line got the full recency score and the oldest none, as much weight as the whole of relevance. Recency is now the real fade (0.995 an hour), which barely moves within an hour.
- **A trim rule must never remove the only item.** The guard's `cut` drops the last item of a section line and, with one item left, the whole line; for a line that exists to carry one memory, that is the same as never adding it.
- **The rules' retargeting read whole statements as a new target (23 October 2026).** While following, finding or looking, any clause starting with "the", "my", "that" or "this" became "follow the X": 17 of 40 everyday lines switched a follow to "the kid", "the bus" or "the tomatoe". The reader sets never had chat during an activity; the long-talk eval did. It now takes at most three words after the determiner.
- **One llama-server, one client while measuring.** The CUDA server runs 4 slots on one unified 8,192-token cache; a debugging script run beside a measuring run made a reply fail with "Context size has been exceeded", and the run had to start again.
- **"Warm" is a foreground purpose in the llama client** (read-ahead must beat a background turn), so it can't be cut off when someone starts talking; anything warmed in quiet time needs a background purpose (`ready`, `rewarm`).
- **Where an instruction sits in the system text matters to E4B (23 October 2026).** Moving the frozen turn guide and faces in front of the self text, so a nightly change re-reads fewer tokens, cut a life turn's tool calls from about 30 of 75 to 10; it went back. Measure the tool evals after any reordering.
- **The 3-characters-a-token estimate is right for talk and about 40 % high for prose.** Full notes are 297 real tokens and 433 estimated. Plain code that packs a row by the estimate under-fills prose rows but never gets cut by the guard; a read-ahead the guard would trim now counts with the real tokenizer first.
- **On Windows, `Path.write_text` turns every newline into CRLF.** Edit files as bytes, and check both kinds of line endings after a scripted edit.
- **A test set of made-up skills needs made-up differences.** Random step mixes gave 200 skills that a three-step description couldn't tell apart; real skills differ by where they go, whom they look at and what they show, so the year-old self's skills do too. The same run showed that one shared word (a "sleepy" face against a "sleepy wiggle") outranked the description, so a skill now counts as named only by its whole name or an alias.
- **Pebble script decisions (23 October 2026):** one host process per running program (a hung or crashing one can't take another's values or time); refusals that are wrongdoing count toward the three that pause a program, "not now" ones don't; questions refused return an empty answer, so a loop over `look()` can't walk the letters of "refused: ..."; `chance()` and `pick()` come from the brain's chaos stream, so the evaluator has no randomness and the vectors replay exactly; scripts on the phone only dream until S7 flips `LIVE_ON_PHONE` in `script/live.py`.
- **Hand programs the names they will compare with (23 October 2026).** E4B wrote `if who != "sam": return` against `FOR = "sam"` and got "Sam", so a joke-on-arrival program never spoke; names now reach programs in small letters, as in `FOR`.
- **A dream day must be a day someone could live (23 October 2026).** Feelings and sightings spread over 24 hours landed at 23:00, and a dance-when-happy program failed its dream for moving in quiet hours; events are now laid in waking hours only. Likewise a count is checked against the events up to the moment it was said, not the whole day, and a clock time in a line ("at 03:30") is not a count.
- **A fix round starts from the first prompt and the last attempt only.** Carrying every attempt forward would pass the 8,192 window by the fourth round; the model only needs the last try and its error lines.
- **Score the first look, then tune (23 October 2026).** The writing eval's 40 tasks scored 70 % on the first run and 92 % after changes made while reading their failures; the second number flatters, and a fresh set is needed before trusting it.
- **Windows job objects from ctypes need `argtypes`.** Without them the 64-bit handle is cut and `SetInformationJobObject` quietly fails, so the host process ran with no memory limit until a test that allocates 200 MB caught it.
- **`bindIsolatedService` instance names take only letters, digits, `_` and `.` (23 October 2026).** A hyphen made Android throw "Illegal instanceName", and every program's process failed to start until the name changed.
- **An isolated process still runs the app's `Application.onCreate`,** with most system services missing (the notification manager is null), so anything there must check `Process.isIsolated()` first.
- **A heap ceiling measured as total minus free counts garbage.** The Kotlin evaluator's tight test loop passed 64 MB of uncollected garbage within seconds and the guard called it out of memory; it now collects once and measures again before ending the process.
- **Test a port on more than its vectors.** A one-off replay of 141 more programs written by the Python evaluator (the red team, the starters, edge cases of floats, text, sorting and errors) agreed with the Kotlin port on every call and outcome; its only mismatch was the harness, which recorded a reply after the Python program had changed that same dict in place. Record replies as copies.
- **`am instrument` force-stops the whole app** (keeper, brain, ears) before it runs, so start the face again afterwards (`am start -n nz.pebble.robot/.ui.HomeActivity`). `gradlew connectedDebugAndroidTest` uninstalls the app when it finishes, which would take the emulator's self with it; install with `adb install -r -t` and run `am instrument` instead.
- **Inside an isolated process the app's data folder isn't there at all** (`ENOENT`, not `EACCES`, for files the app certainly has), and sockets fail as they are made (`EACCES`), local ones too, because the process isn't in the network group.
- **The Bash tool also turns `\u` escapes in a command into the characters themselves,** so a Python heredoc with `\u200b` in it ran with a real zero-width space. Write such scripts with the Write tool and run the file.
- **Teaching decisions (23 October 2026):** plain code replays what was shown at once and always makes its own version, so teaching works with no model and Gemma only generalises it in the background; the kind comes from how it was shown (E4B called 8 of 29 moves procedures), and Gemma's kind only decides between what that leaves; habits live in the how-to book and are checked against the event feed, not kept as agenda items, which run out after 7 days; the pad has no chirp buttons because this body has no buzzer; leading is the ordinary follow, so it gets the follow request's gate; always-private rooms are refused when taught and again when run; examples keep only a short name of what was asked, never the teacher's sentences; a concept's look is read while Pebble is idle (every 10 s, kept 60 s), so a condition on it never makes Pebble stop and look.
- **A cache must hand out copies when its callers change what they get (23 October 2026).** The how-to book's cache returned its own entries; the second lesson of "check the kitchen" changed the stored entry in place before its checks ran, so the first lesson's copy grew a slot too, and a refused change would have stayed in memory. `HowTo.get` now returns a fresh copy.
- **E4B writing a taught lesson needs the body's card as a grammar.** Without it, it wrote steps as `{"turn": {...}}`, wrote turns as request trees, and sometimes wrote JSON that didn't parse; with the card's blocks as the only step shapes, 27 of 29 lessons passed the checks.
- **A sim measurement must stop with the thing it measures.** The lead scene kept recording Pebble's track after the taught way ended; Pebble went off to look at a slipper and the "distance from the path" read 1.15 m. The track now stops when the route ends.
- **Waiting in a sim scene until nothing runs never ends** when the activity is meant to keep running (wait, follow, copy me, the pad's drive); the teaching scenes count those as quiet unless a replay is playing.
- **Reading AliExpress prices:**
  - Search pages can be fetched as HTML and parsed for `"productId"`, `"displayTitle"` and `"formattedPrice"`.
  - Listing pages are drawn by script: click each `[data-sku-col]` and read `[class*="price-default--current"]`.

## Still unverified (needs real hardware)
- Nothing has run on the real robot or the phone yet: the face page, voice, vision, dock homing, the passphrase flow, and every speed and timing.
- Pebble script on the phone has run only in the emulator's tests: the isolated service, its sandbox and the 15 starters through the bridge; never a living Pebble's programs on the Pixel, and not the evaluator's speed on its cores.
- **Link security:** BLE and TCP currently accept anyone, so the link needs authentication. Per-line checksums on BLE are also missing.
