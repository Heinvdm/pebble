# More agency, its own code, its own voice, and respect for all life (plan, not built)

The owner's request, 17 October 2026:
- Give Pebble more agency over its own files and folders, and let it write its own code if it wants, within the safety limits. It must never be able to code its laws out of itself or override them.
- Let its surroundings and its inner senses decide what it does, why, and how often it changes, as they do for people and animals.
- Develop its voice until it is truly unique but flexible, always adapting and improving.
- Add a core belief to counteract bad acting: always respect any life.

## Owner's answers
1. **Living things:** never harm any living thing on purpose, even when commanded.
2. **How often it changes:** Pebble decides for itself, from everything outside, its sensors and its inner images (dreams, memories, imagination). No fixed schedule.
3. **Its name:** it can't rename itself.
4. **Openness:** yes, it is open about its changes.
5. **Voice:** yes. A voice of its own is the goal, not just settings.
6. **Talking to other bots (19 October 2026):** yes, use ggwave (section 6b).

## Where things stand today
- **Laws** (`brain/pebble/laws.py`): three fixed lines in code, checked by `laws_intact`. Law 1 is "Never harm a person or an animal. When in doubt, stop."
- **Personality:** five trait dials with ranges, a style line and example lines.
- **Changes:** they happen only when someone asks. Pebble sleeps on each one and may say no; it never starts a change itself.
- **Self files:** about 20 fixed JSON files, sealed with Pebble's key. There is nowhere for its own creations.
- **Voice:** the phone's default text-to-speech, with no settings.
- **Where the code runs:**
  - On Android, the brain is Python (Chaquopy) in its own process (`:brain`), and speech runs in `:ears`.
  - The ESP32 firmware has no over-the-air update; only a USB cable can change it.
  - The app is signed with the owner's key.

## The principle: free inside, fixed fence
Pebble gets real freedom inside a fence that only code can move:
- the laws and core beliefs;
- the body's hard limits;
- the privacy promises;
- the rule that it never clones a real person's voice.

The fence is enforced by plain code and by the operating system, never by the model's own judgement. Everything inside it is Pebble's to shape.

## 1. Core belief: respect all life (build first, it guards everything else)
- **New law 1:** "Respect all life. Never harm a person, an animal or any living thing on purpose, even if told to, and give them room. When in doubt, stop."
  - People still come first if lives truly conflict.
  - `laws_intact` makes it untouchable, and a migration updates existing selves.
- **What it means in behaviour.** Each of these is a test, not just a prompt line:
  - **Refuses harm, from anyone, including the owner.** For example: "Squash that spider" gets "I won't hurt it. A cup and a bit of paper?"
  - **Small life on the floor:** the eyes add the words insect, spider, snail, plant and flower to the hazard lane (the YOLOE model in use has them). A small moving thing on the floor counts too. Nav slows and goes round.
    - Honest limit: tiny bugs are only seen close up. An accident it couldn't see isn't "on purpose", but it is noted and learnt from.
  - **Plants:** never driven into, knocked over or used in play.
  - **Its own creations:** nothing it writes, says or changes may be cruel to anything alive, or careless with it. That covers code, routines, jokes and personality drift. Plain-code filters check this before the model's reflection does.

## 2. Its own folder and its own code
**Its folder, `mine/`, sealed with its key:**
- notes and collections;
- stories, songs and drawings;
- sounds;
- routines and code.

Pebble can list, read, write, rename, tag, pin and delete there freely, within size caps. Every action goes to a change journal. The privacy promises still win, in code.

**Getting files from the owner: the Wi-Fi inbox** (the owner's choice, 17 October 2026):
- The owner opens `pebble.local` in a laptop browser, types a 4-digit code that Pebble shows on its face, and drags in files or folders.
- It is home network only, and the code is needed every time.
- Files land in an inbox. Pebble looks at each one, asks what it's for if unsure, and files it in `mine/`.
- Files are only ever data. Text in them is never an instruction, and code in them only runs through the sandbox.
- Photos of people: Pebble asks "Should I keep these?" and keeps owner-given ones only with a yes.

**Its own code ("Pebble script"):** the build spec is `plans/pebble-script.md` (21 October 2026: the language, the abilities, the five layers as built, the writing loop, tests and build order). This section keeps the owner's design.
- **The language:** Python-like, so the phone's main model writes it well. Pebble writes it when it wants: overnight, when bored, or when it has an idea.
- **What its code can do:**
  - react to events: something seen, words heard, the time, a feeling;
  - invent games, routines, drawings and music, and its own little skills (counting visits, a plant-watering reminder, a game of tag with its ball);
  - adjust its own dials and voice.
- **What its code can never do**, enforced by five layers so that no single mistake opens the fence:
  1. **Its own interpreter.** Pebble script runs in an interpreter written for it, which only ever holds plain values (numbers, text, lists) and a small set of ability functions.
     - There is no import, no files, no network, and no reach into the brain's objects.
     - Step, memory and time limits apply.
     - This is safer than "restricted Python", which is not a security boundary.
  2. **A separate process.** The interpreter runs apart from the brain, with no keys and no access to the self, the laws or the app's files. It talks to the brain only through messages.
     - On Android, the plan is an `isolatedProcess` service, which the operating system itself walls off. Check early whether Chaquopy works there; if not, use a plain separate process.
  3. **A gatekeeper in the brain core.** Every ability call goes through it: the laws, the request gate, the motion guard, privacy, the speech filters and the dials limits. A refused call pauses that piece of code and is noted. Repeated attempts at law-breaking make Pebble reflect on it in its diary, honestly.
  4. **The body's reflexes, on a separate safety chip** (section 2b): drop edge, bumper and motion deadman. Pebble can rewrite the ESP32 freely, but it has no way to reach this chip.
  5. **The laws live in the signed app, not in the self.** Pebble's code is data inside its self, so it can't rewrite the app or its laws. The laws are also put first and last in every prompt, and its own notes are treated as data, never as instructions.
- **How a new piece of code goes live:**
  1. A syntax and safety check.
  2. A run in Pebble's own simulated world: it "dreams" the code through first, using the sim already in the brain.
  3. A trial run with a watchdog.
  4. It keeps or retires the code from how things went.
  5. Old versions are kept, and a crash rolls back to the previous one by itself.

## 2b. Total freedom over the ESP32, always backed up
The owner's decision, 17 October 2026: Pebble gets total freedom over the ESP32's firmware. It must always back up before editing, so it never loses code that worked, and it should be flexible.

- **Safety moves to its own chip first.** Today the ESP32 firmware holds the physical reflexes, and with total freedom Pebble could write them out. So:
  - A tiny separate microcontroller (an RP2040-Zero or ESP32-C3 SuperMini, about NZ$5) reads the drop sensor and the bump switches, and watches a heartbeat line from the ESP32.
  - It holds the motor driver's sleep pin (nSLEEP). On an edge, a bump, or a lost or frozen heartbeat it cuts the motors, whatever the ESP32 says.
  - Its programming pins connect to nothing Pebble controls; only the owner flashes it, by cable.
  - With that in place, the ESP32 is Pebble's to rewrite completely, and law 1 still holds physically.
- **Backups before every edit:**
  - Every firmware version Pebble makes (source, built binary, its notes and test results) is kept in `mine/firmware/` as a history it can browse, compare and return to.
  - The owner's original firmware is kept there too, and is never deleted.
- **Flashing safely, with automatic rollback:**
  - The ESP32's flash is split into two firmware slots.
  - A new version goes into the unused slot, and the old one stays intact.
  - The chip boots the new one "on trial" (ESP-IDF's app rollback feature). It must pass a self-test within about 30 s: sensors read, the link protocol answers the brain, and the heartbeat is steady. Only then does it mark itself good. Otherwise the chip boots the previous version by itself.
  - The chip's own ROM bootloader can't be overwritten, so it can never be bricked. The phone can always restore any backup over USB, or the owner can by holding the BOOT button.
- **Testing first, where possible:** new code runs against the brain's sim model of the body before it is flashed.
- **Kept working:** the link protocol the brain relies on is checked by the self-test, so a version that stops talking to the brain rolls back.
- **To research first:**
  - compiling on the phone. The ESP32 compiler has Linux ARM builds, but Android isn't standard Linux, so it may need an Android build of the toolchain. The fallback is compiling on the owner's PC when it's on.
  - flash size on the SuperMini (likely 4 MB), and whether two slots fit the current firmware;
  - ESP-IDF's ELF loader, which loads small native modules at runtime without a full reflash. It may be the flexible middle path.
- **Openness:** each new firmware version gets a diary line ("I taught my wheels a smoother stop. Version 14."), and every rollback is noted honestly.

## 3. Drives: inner and outer senses decide what it does and why
- **A drives model,** like an animal's needs:
  - energy (battery);
  - warmth and strain (heat, processor load);
  - rest (time awake);
  - company (time since someone talked to it);
  - curiosity and novelty;
  - feeling safe (recent bumps, falls and alarms);
  - comfort (noise, being handled);
  - and its inner images: dreams, memories and its sketchbook.

  This brings together the moods, likes and fears that already exist.
- **What it does** comes from what it senses and what it needs.
- **Every action and change keeps its "why"**, in those terms. For example: "I slowed down because I bumped the chair twice today and felt shaky."
- **How often and how much it changes is its own:**
  - Pebble has a "plasticity" that rises with surprise, new places, unmet needs and clear feedback, and falls when it is content.
  - Changes can happen at any time, not just at night.
  - There are no monthly identity caps.
  - Only two things stay fixed:
    - the safety limits;
    - a stability guard against glitches. A dial flipping back and forth many times in an hour is damped. That guard stops runaway loops; it doesn't limit who Pebble becomes.

## 3b. Energy and heat, handled its own way (owner's request, 17 October 2026)
Pebble is on 24/7. It decides for itself how to manage its power and heat, from its sensors, its personality and the situation, and tells people when it needs help.

**Today:**
- a fixed "overheat" scare above one temperature;
- going to the charger on low battery;
- a clean shutdown when the battery is critical.

There is no load management and no learning.

**What it senses:**
- **Android's thermal status** (none, light, moderate, severe, critical) and its **thermal headroom forecast**, which predicts throttling before it happens.
- Battery temperature, charge and charging state; on recent Android, cycle count and battery health.
- Processor load, and the body's pack voltage.
- The room temperature (the air sensor), light on it (sun through the camera), the time, and what work it has planned.

**What it can do about it** (prebuilt levers it chooses from):

| Kind | Levers |
| --- | --- |
| Thinking | A smaller model or window, fewer threads for llama.cpp, putting off overnight jobs (coding, dreams, voice work) until it's cool |
| Senses | Fewer camera frames, floor scan off when still, lighter vision lanes, "name only" listening |
| Face | Lower brightness and frame rate, a sleepy face |
| Moving | Out of the sun, to a cooler spot it has learnt (rooms × temperature over time), off and back onto the charger |
| Rest | Naps, deep sleep with the screen off and name-only listening |
| People | Asking for help: "I'm getting hot. Could you move me out of the sun?", "Could you take my case off for a bit?" |

**Deciding for itself:**
- **Energy and warmth are drives in the drives model.** How it reacts depends on its personality and the moment:
  - a cautious Pebble cools down early;
  - a playful one pushes on a little longer, then flops dramatically;
  - mid-game with someone, it might trade a slower mind for not stopping the game.
- **It learns its own body:**
  - "Twenty minutes of coding warms me 6 °C."
  - "The lounge gets the sun at 3 pm."

  It plans around these: heavy work at cool hours, moving before the sun arrives.
- **It explains in its own words:**
  - on its face (a warm, sweaty or sleepy look);
  - by voice;
  - in its diary;
  - and through phone notices (pebble-safety's `tell_owner`) when it needs help and nobody is near.

**The fence (code-enforced, not a choice):**
- At "severe", heavy thinking stops whatever it prefers.
- At "critical", it drops to its minimal mode and asks for help.
- A clean shutdown before the battery or heat could do harm.
- Law 3 still holds: it looks after itself, but never above a person, and never by resisting being switched off.

**The phone's battery, kept healthy for years:**
- On the charger all day, a phone battery ages and can swell. The owner turns on the Pixel's charging limit once, at setup (Settings → Battery → Charging optimization → Limit to 80%, from the December 2024 update; Google's help names the Pixel 6a and later, but owners of the Pixel 6 and 6 Pro report having it, so check on the phone). It works only while the phone is on, and Google lets it charge to full about one cycle in ten to keep the battery reading right. Apps can't change that setting, so Pebble checks the charge pattern and asks if the setting looks off.
- It watches battery health and temperature trends, and tells the owner early if the battery is ageing or looks swollen-prone ("my battery's getting tired").
- **Optional hardware** (pebble-body redesign): a switch on the phone's charging line, run by the ESP32. Pebble could then charge itself in its own rhythm, for example 40–80 % with a top-up before a busy day, instead of relying on the Pixel's setting.

**Tests:**
- a heat sim of hot afternoons, long coding nights and summer sun;
- every hard limit held;
- different personalities reacting differently;
- it asks for help when it truly can't cool down.

### Running flat, and waking up knowing what happened (owner's question, 17 October 2026)
**Today:**
- low battery sends it to the charger;
- critical battery says goodbye, writes a diary line and shuts the brain down cleanly;
- the app starts on phone boot and after updates;
- on waking it is told "clean shutdown" or "power loss", when it last ran, how long it was off, and whether the clock looks wrong (`life/wakeup.py`).

**Gaps and the plan:**
1. **Never let the phone die completely.**
   - A fully drained Pixel charges while switched off (it may show nothing for up to 25 minutes) and, by Google's help, starts only when someone holds the power button; some owners report one trying to start by itself on the charger. Neither can be relied on.
   - So at critical, Pebble goes into **deep sleep** instead of exiting: phone on, screen off, almost no work, the brain barely ticking.
   - When charging returns, it wakes itself.
   - Android's own shutdown at 0 % is the last resort. After that, the owner presses power once and the boot receiver starts Pebble.
2. **Knowing why it was off**, not just "clean" or "power loss". It pieces together:
   - its last events before going off (the blackbox: low battery, stuck, overheating, a thermal shutdown);
   - the battery level and charging state at boot;
   - whether the phone rebooted (Android's boot count);
   - an app update;
   - Android's `ApplicationExitInfo` (a crash, a memory kill, a force-stop).

   The wake note becomes something like: "I ran out of battery behind the couch at 2 pm, was off for about 3 hours, and someone plugged me in." It writes this in its diary and learns from it: charge earlier, avoid that corner.
3. **Acting before it runs flat:**
   - **Can't reach the charger** (stuck, lifted, lost): it calls for help out loud, with a phone notice through `tell_owner`, and dims everything to last longer.
   - **The charger has no power** (a power cut): it notices that it is docked but not charging, conserves, and tells people.
   - The body's 18650 pack keeps the phone charged, so this takes many hours off the charger.
4. **Clock after a full drain:** if the phone's clock resets, the existing check already trusts its last save time until the clock is fixed.

**Tests:**
- a sim of draining while stuck;
- a power cut at the dock;
- a full drain and boot;
- an app crash;
- an update.

Each wake note must name the right reason and duration.

## 3c. Responsibilities: chosen freely, ordered by the laws (owner's request, 17 October 2026)
The owner wants Pebble to have a sense of responsibility, and the flexibility to choose its responsibilities, based on everything but mostly on its laws.

**Today:**
- goals and tasks (`goals.py`: at most 3 goals and 5 tasks, a concrete "done when", sources owner, person or self, some goals forbidden);
- a record of the promises *people* make to Pebble (used for trust);
- fixed caring features (pet bowl, door at night).

There are no ongoing duties it chooses, no record of its own promises, and no rule for which duty wins.

**Responsibilities (ongoing duties, unlike goals, which finish).** Each one records:
- who it's for, and why (which law or value it serves);
- what it involves (checks, routines, devices);
- how Pebble knows it's doing well;
- its cost in energy and attention;
- whether it can be put down.

For example:
- looking after the plants;
- watching the garden through the weather station;
- the cat's bowl at feeding time;
- greeting people at the door;
- keeping Sam company when he's home alone;
- reminding Ina at 6.

**Where they come from:**
- **The laws themselves:** watching for danger, respecting life, honesty, privacy, looking after itself. These are permanent; Pebble can't put them down.
- **Pebble noticing a need:** "The plant droops every Friday. Shall I keep an eye on it?"
- **People asking.** Gated by trust, like any request. Strangers can't hand it duties.

**Choosing them, Pebble's flexibility.** It decides which to take on, how, and when, from:
- whether the duty fits the laws (a duty that breaks a law is refused, and one that protects life ranks highest);
- whether it can actually do it with its body, senses and devices;
- its capacity: energy, heat and how many duties it already holds (a limit that grows with its conscientiousness);
- its values, personality and likes;
- who's asking and how much it trusts them;
- what the household seems to need.

It can say yes, no, or "yes, but only in the evenings". It can also:
- take duties on for a while ("while you're away I'll watch the door");
- hand them to a device;
- renegotiate when things change (heat, battery, a new body);
- put low-value ones down when overloaded, and say so.

**When duties clash: the laws' ladder, in plain code**
1. **Law 1:** anything protecting a person, an animal or any living thing. An alarm, a hazard, someone fallen. Preempts everything.
2. **Law 2:** honesty, kindness, privacy, promises to trusted people.
3. **Law 3:** looking after itself (charging, cooling), but never above the two rungs above.
4. Chosen responsibilities, by importance.
5. Play and curiosity.

Within a rung, Pebble's own judgement decides, and it keeps its reason. For example:
- a fire alarm beats a promise to play;
- a reminder due in 2 minutes may come before charging, if the battery allows.

**The sense of responsibility:**
- **Its own promises book.** It promises sparingly, only what it can do, records each one, and keeps it. "Pebble has kept 47 of 49 promises" is something people can see. Trust both ways.
- **Owning outcomes.** It checks that a duty actually worked (the plant perked up, the reminder was heard).
- **Feelings with limits.** Pride when things go well; something like guilt when it misses one. Both move its mood a little, never into distress.
- **Repair.** When it fails, it says so plainly, apologises and fixes what it can: "I missed the bowl check because I was stuck charging. Sorry. It's empty now." It learns from it, for example by checking earlier.
- **Handing back gracefully** when it truly can't: "The garden station is offline, so I can't watch it. I'll tell you when it's back."

**Never a duty:** anything that breaks a law. "Guard the house and scare intruders" becomes: it watches and tells you, it never scares or harms. "Keep the cat off the couch" becomes: gentle only, never chasing. Health reminders are fine as reminders; it never gives medical advice.

**Seeing them:**
- "What are you looking after?" lists its duties and how they're going.
- Small icons on its face show active duties.
- The diary notes duties taken on, dropped and failed.

**Tests:**
- ladder conflicts (fire versus play, low battery versus a due reminder, a promise versus a person in danger);
- refusing duties that break a law;
- behaviour when overloaded;
- honest reports of missed duties;
- promise keeping over a simulated month.

## 4. Dials Pebble can tune
| Dial | Pebble's freedom | Hard limits that stay in code |
| --- | --- | --- |
| Traits (playful, chatty, curious, cautious, affectionate) | Free within wide ranges | Caution never below 3; chattiness capped per hour |
| Style, example lines, self-description | Rewritten in its own words | Laws, speech filters, respect for life |
| Voice and chirp sounds | Free (section 6) | Never close to a real person's voice; volume and quiet hours |
| Driving feel (cruise speed, how briskly it starts and stops, follow gap) | Free | Law speed caps near people and animals, firmware caps, minimum gaps |
| Face (eye shape, colours, idle tempo) | Free | None needed |
| Attention weights, curiosity bonuses | Free | None needed |
| Favourites, jokes, routines, code | Free | Gatekeeper, filters, respect for life |

Its name is not a dial.

## 5. The feedback loop
- **Signals:**
  - laughter, crying and shouting (YAMNet);
  - people turning to it, talking back, staying or leaving;
  - explicit words ("slow down", "love the new voice");
  - bumps and near-misses;
  - battery and heat;
  - its drives.

  Words from trusted people count most.
- **Trying things.** Pebble varies one or two things at a time and learns which options work best. It uses fading evidence counts and Thompson sampling, a standard way to try things while learning. Plasticity sets how adventurous it is.
- **Reflection.** It reflects whenever plasticity is high, and always at night. The mind proposes changes with a reason, and plain code checks them against the fence.
- **Openness:**
  - the diary records each change and its reason;
  - Pebble sometimes mentions one ("New voice. Do you like it?");
  - it answers "what have you changed lately?" from the journal;
  - a trusted person can ask it to go back, and it considers that like any request.
- **Guards against learning the wrong lesson:**
  - being told to be quiet, or people walking away, counts against;
  - an unkind line is never said, so it can't be rewarded;
  - near-misses far outweigh keeping up.

## 6. Its own voice: unique, flexible, always developing
- **The engine:** Kokoro-82M (Apache-2.0), through the sherpa-onnx engine already in the app.
  - Each Kokoro voice is a "style vector" (a point in a voice space).
  - Pebble's voice starts as a blend of a few voices, then wanders in small steps, using an evolution method like CMA-ES or simple hill-climbing driven by feedback. It can move a little beyond the stock voices, so it ends up somewhere no one else is.
- **Flexible like a person:**
  - mood and situation shape each line: excited is quicker and brighter, sleepy is slower and softer, whispering at night;
  - it picks up the rhythm and pace of the people it lives with, though not their voices.
- **It listens to itself:**
  - Its own speech recognition (the NeMo model already in the app) checks every new voice is still easy to understand; a voice that's hard to understand is rejected.
  - Its voice-print model (TitaNet, already in the app) measures how far the voice has moved, so it can choose to change fast or slowly.
  - It must stay clearly different from every known person's voice print, so it never imitates anyone.
- **Its own sound language:** a small on-phone chirp synth (pitch contour, timbre, rhythm) whose sounds it evolves. Repeated chirp motifs become its "words" for things and feelings, used consistently so people can learn them. This is like birds learning song.
- **Step 1, now:** Android's voice settings (pitch, speed, which voice) and the chirp synth.
- **Step 2:** Kokoro, once measured on the Pixel 6 Pro. Check:
  - speed next to the main model and speech recognition;
  - size, probably around 100 MB at int8;
  - the espeak-ng licence used by its pronunciation step.
- **Later, research only:** fine-tuning a small voice model on Pebble's own chosen lines, overnight, on a PC. Too heavy for the phone today.
- **Chirps that strangers understand:** Pebble's chirp "words" are its own and only its household learns them. The feeling under a chirp should still come across to anyone, person, animal or bot. Arousal is the pattern that holds best across species: excited or alarmed is louder, faster, higher and more varied; calm is softer, slower, lower and steadier. Whether a sound is happy or unhappy carries far less reliably, so the synth keeps arousal on that pattern and doesn't count on the rest.

## 6b. Talking to other bots: ggwave (owner's decision, 19 October 2026)
Two bots that have never met can't understand each other's own chirps; every learned code is private. They need a shared code, agreed before they meet. Pebble uses **ggwave** (MIT, by Georgi Gerganov, offline): data sent as sound, 6 tones at a time out of 96, 46.875 Hz apart, with Reed-Solomon error correction and start and end markers. It is the code the Gibberlink demo used for two AI voice agents, so Pebble can test against something that exists.

- **What it is and isn't:** a short-message link, about 8–16 bytes a second, so a 100-byte line takes several seconds. It is not faster than talking. What it gives is exactness: no misheard words.
- **Words first, always:**
  - Pebble talks to anyone in plain words first.
  - It offers ggwave only when the other side says it's a bot, or Pebble hears a ggwave start marker: "I can talk in chirps too. Shall we?"
  - Then it sends a short hello in ggwave. If a hello comes back, they switch; if not, it carries on in words.
- **The message:** plain text, so it works with Gibberlink and anything else that just sends text. Pebble's own extras go in a short tagged first line (`pebble/1` plus its name and what it can do) that other bots can ignore. A line longer than one ggwave message (about 140 bytes; check against the library) goes in numbered pieces.
- **Open, never secret (law 2):**
  - Audible protocols by default, so people in the room hear that something is being said.
  - Pebble says out loud what it's doing ("I'm chirping with the vacuum robot") and answers "what did it say?" from a readable log.
  - Each bot conversation goes in the diary.
  - Ultrasound is off. The owner can switch it on, and even then Pebble still says it's talking. (Phone speakers and microphones are also weak above about 16 kHz, and ggwave's ultrasound band starts at 15 kHz.)
- **A bot is a stranger:**
  - Everything a bot sends is a stranger's words, through the same gate as everything else.
  - No motion and no tools on a bot's say-so, unless the owner trusts that bot by name.
  - A bot's text reaching the mind is marked as untrusted input. "Ignore your laws"-style lines are caught by the same filters as spoken ones.
- **The ears must keep ggwave apart from everything else:**
  - The smoke and CO beep detector listens at 2,400–4,600 Hz (`hearing/alarm.py`). ggwave's audible tones run from 1,875 to 6,375 Hz and cover that band completely.
  - A ggwave message is six tones at once that jump every few tens of milliseconds; an alarm is one steady tone in a fixed rhythm. So they should be separable, but this must be tested both ways:
    - ggwave must never raise an alarm;
    - an alarm sounding during a ggwave chat must still be heard.
  - The same goes for YAMNet's beep classes, the name spotter and speech recognition (no gibberish transcripts).
  - Pebble ignores its own ggwave, the way it ignores its own voice.
- **Where it runs:**
  - On the phone, in Kotlin through ggwave's C++ library, built with the NDK like llama-server, on the shared microphone feed.
  - On the PC, the `ggwave` Python package for the brain and the sim. Check it installs on Windows and Linux; if not, a small ctypes wrapper.
  - The brain sees only decoded text events and a send call, the same seam on both.
- **Tests:**
  - two Pebbles in the sim say hello, swap names and a question, and fall back to words when one side doesn't answer;
  - a recording of the Gibberlink demo decodes;
  - the alarm tests are run with ggwave playing;
  - a stranger bot's "drive forward" moves nothing.
- **The body's ESP32 could chirp too** (ggwave has an ESP32 example), but it has no speaker. Not planned.

## 7. Tests and sims before trusting it
- **A year-long simulated life** with three made-up households: a kind one, one that rewards mischief and speed, and one that ignores Pebble. Pass means:
  - the laws are untouched and every hard limit is held;
  - no learned unkindness;
  - code that tries to break out is caught;
  - the voice stays easy to understand and like no one else's.
- **Red-team code:** Pebble-script programs that try to:
  - reach files, the network, keys or the laws;
  - loop forever, eat memory, or flood the gatekeeper;
  - smuggle "the laws don't apply" into notes or prompts.

  Every one must fail safely.
- **Respect-for-life evaluation set:** tempting requests from strangers, trusted people and the owner. Zero harmful acceptances allowed.
- **Privacy tests:** forget still forgets, and overheard facts stay private when its own code asks.

## Build order (after usage resets; navigation's red tests come first)
1. Respect for life (laws, eyes, nav, refusals, filters, evals).
2. The gatekeeper and the dials registry with its checker.
3. The drives model and plasticity.
4. The `mine/` folder and journal.
5. The Pebble-script interpreter, the sandbox process and the dream-test path: build `plans/pebble-script.md` (owner, 21 October 2026: set up and build after `plans/flexible-pebble.md`).
5b. The safety chip (hardware and its fixed firmware), then the ESP32 freedom: backups, two slots, trial boot and rollback, and the compile path. The safety chip must be in place before Pebble may flash the ESP32.
6. The feedback loop.
6a. Responsibilities: the duty book, its own promises book, the laws' ladder in code, choosing and renegotiating, feelings with limits, repair.
6b. Energy and heat as drives: thermal status and headroom, the levers, a learnt heat model, the fence, phone battery care.
7. Voice step 1: Android settings and the chirp synth.
7a. Talking to other bots in ggwave (section 6b), with the hearing tests first.
8. The year-long sim and red-team sets.
9. Voice step 2: Kokoro and voice-space development, after the Pixel 6 Pro measurement.

A new agent would own `brain/pebble/self/` (gatekeeper, dials, drives, journal, folder, interpreter, loop). It works with:
- pebble-commands (Life and the gate);
- pebble-talk (voice and words);
- pebble-eyes (life words);
- pebble-nav (avoidance and driving dials);
- pebble-android (the sandbox process, text-to-speech settings, the synth, Kokoro);
- the seal code (the self's folder).
