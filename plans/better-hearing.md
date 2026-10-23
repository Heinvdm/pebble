# Better hearing: calls from another room, sounds people can't hear, and which way a voice came from (plan, not built)

The owner's questions, 19 October 2026: can he call Pebble from another room, and can Pebble pick sounds apart and hear things people can't? He then said "yes, plan it" to the five items below.

The short answer:
- **Calling from another room** can work for the name and short calls, much less for whole sentences. From afar Pebble is less sure, so it says "Coming!" when it is sure and "Was that me?" when it isn't, then goes to where the caller usually is or where the sound came from, and listens up close. Who may send it round the house doesn't change.
- **Pebble hears nothing above 8 kHz today,** because the microphone runs at 16 kHz. At 48 kHz it could hear up to about 20–24 kHz, if the Pixel's microphone path lets that through, which must be measured. That reaches charger and power-supply whine, the 17.4 kHz "Mosquito" tone, ggwave's ultrasound band (15–19.5 kHz) and the 18–20 kHz beacons some apps use. Most pest repellers sit above 24 kHz and stay out of reach.
- **Which way a sound came from** depends on one thing only the real phone can answer: whether Android hands over two raw microphone channels. Pebble checks that by itself, with a click from its own speaker.
- **A clean-up model before speech recognition** often makes recognition worse, not better. It is tried only on far or noisy speech, as a second listen, and kept only where it measures better.
- Nothing has run on the phone. Every distance, speed and accuracy below is an estimate until item 1 measures it.

## Owner's answers
**20 October 2026, the two that were open:** the public test clips re-recorded through the phone may be kept on the PC for 30 days (debug build, owner-started sessions only, the clips' own time slots). A far caller's spoken name ("it's Ina") counts for "come here" only, never for anything that needs trust. Also decided that day in NOTES.md: Pebble wakes to its name at night, and it stops talking whenever any voice starts.

Given 19 October 2026, "yes, plan it", to all five:
1. **Measure first:** how well Pebble hears on the real Pixel 6 Pro, recorded as numbers only, with no recordings in the repo.
2. **Called from another room:** within the trust gate, quiet hours and nav's safety.
3. **A high-pitch listener,** with patience-and-memory listening for recurring sounds.
4. **A clean-up step before speech recognition,** on the ladder, measured against the speech evaluations.
5. **Turning towards a voice,** if the phone gives its microphones separately.

Already decided, and binding here (`reports/More everyday value for the household.md`, owner's answers):
- The household pack is built right after Android round 3, and this plan is part of it. It is the full design for A16 ("which way a sound came from", in the pack if the phone gives two raw channels), and it adds to A4 (teach Pebble a sound) and A5 (the chirping smoke alarm).
- No microphones in other rooms and no Bluetooth sensors. Everything here uses the phone's own microphones.

Later that night the owner asked for the recommended answers to this plan's questions. They are recorded as his answers:

| # | Question | Answer (recommended, taken) |
| --- | --- | --- |
| 6 | A far call from a stranger, or from a voice Pebble can't match to anyone | It answers from where it is ("I'm here, in the lounge!") and turns towards the sound. At most it goes to the door of the room it is in. It never goes into another room for them. |
| 7 | A far call in quiet hours | No driving. If name spotting at night is on, a soft "I'm resting. Come and find me if you need me." A shouted name or a call for help goes to the safety ladder, as today. |
| 8 | How loud "Coming!" and "Was that me?" are | A raised voice: one step louder than its normal voice. Never the alarm voice, never in quiet hours. |
| 9 | How long it looks for the caller | Up to 2 minutes after it gets there, then "I couldn't find who called me." and back to what it was doing. |
| 10 | A far call while Pebble is busy | The rule for requests: someone more trusted than the person it is busy with replaces the activity; anyone else hears "I'm busy with Tui right now." |
| 11 | How often it asks "Was that me?" | At most three times an hour. After that, unsure calls are only noted. |
| 12 | Bathrooms and bedrooms | On a far call it stops at the door and asks "Can I come in?" |
| 13 | What a far answer may say | Nothing private: no overheard facts, nothing said "between us", nothing it would only say alone with someone. A raised voice carries through the house. |
| 14 | Words from another room that weren't said to Pebble | The safety code still reads them. Nothing else keeps them: not the 5-minute window, the gist or the overheard facts. |
| 15 | Far voices and voice prints | A far voice never updates a print, and gets no lower bar: a print counts at 0.40, or at 0.28 with that person here or tracked, exactly as up close. |
| 16 | Telling people about high tones | A new steady or pulsing high tone: once, to a trusted person, by day. Data tones: at most once a day. Anything, when asked. Never at night. |
| 17 | When the high-pitch listener runs | All the time, if the probe finds a feed that carries the band and loses nothing today's feed has. Otherwise only on request, for 2 minutes. |
| 18 | Recurring sounds: what is kept | Numbers only, sealed in the self. Full detail for 30 days, then only each sound's summary, as the storage plan does. A stretch where speech is heard never becomes a recurring sound. |
| 19 | Turning to sounds it can't see | Its name, a call for help, a knock, glass breaking or a crash: eyes, head, then body on the spot, under the rules for turning to a speaker (not on the charger, not in quiet hours, not during an alarm). It never drives towards a sound by itself, except for item 2's calls and the safety ladder. |
| 20 | The clean-up step | Only on far or noisy speech, as a second listen, and only where the evaluations show fewer errors. Voice prints, the alarm listener and the sound model stay on the raw sound. |
| 21 | Kit for the check above 20 kHz | Yes: a piezo tweeter on the PC's sound output, or an adjustable dog whistle; a few dollars. |
| 22 | A microphone array on the body (the household report's C3), if the phone gives only one channel | Not now. Asked again only if the probe fails, with prices. |

Two questions stay open, because the recommended answer would loosen a privacy or trust rule: keeping re-recordings of the public test clips, and a spoken name counting for a far caller (see "Still open").

## What exists today
**The microphone** (`android/app/src/main/java/nz/pebble/robot/brain/Microphone.kt`):
- One feed: `AudioRecord` at 16 kHz, mono, 16-bit, in 20 ms chunks. The source is `VOICE_RECOGNITION` (no automatic gain), or `VOICE_COMMUNICATION` by setting. Android's echo canceller is attached when the phone offers it.
- It feeds three listeners in the brain's process: the speech models in `:ears` (over a Messenger), the sound tap (the last 10 s, in memory) and YAMNet's scores (`SoundScorer.kt`).
- At 16 kHz nothing above 8 kHz is in the feed, so Pebble hears nothing high today.

**Words and the name** (`SherpaEars.kt`, `brain/pebble/speech/engine.py`):
- NeMo's streaming recognizer, measured on the PC: 2.9 % word errors reading aloud, 25 % in meetings on a headset, 46 % "across the table, like Pebble". Speech is scaled towards −23 dBFS before recognition (at most 30 times louder); on quiet, far speech that alone took the errors from 65 % to 46 %.
- The name spotter (zipformer; the name's threshold 0.15 and boost 2.0, set in `conversation/listening.py`) hears every chunk raw, without that scaling. It found "Pebble" in 24 of 30 synthetic clips and fired falsely once in 30 minutes of meetings. The silence flush makes it quick, about 0.12 s.
- Voice prints (TitaNet-S) match at 0.40, or at 0.28 with that person here or tracked (`conversation/speakers.py`). On meeting talk from across a table they mix two people up 12 % of the time.
- These numbers were scored by hand in the build sessions. There is no evaluation script in the repo; `python -m pebble.speech.fetch --samples` fetches only two LibriSpeech clips.

**Sounds** (`brain/pebble/hearing/`):
- The beep detector (2.4–4.6 kHz) for smoke and CO alarms, loudness and shouts (`level.py`), and YAMNet's scores turned into notices (`events.py`).
- The YAMNet file Pebble ships also outputs 1,024 numbers describing each second of sound (`embeddings`, made by `tools/export_yamnet.py`), but `SoundScorer.kt` reads only `scores`.

**Being called, today:**
- The name at the start or end of a turn adds +4.0 to "addressed" (`conversation/address.py`). Pebble turns its eyes, then head and body, to whoever it can see speaking (`alive.face_speaker`: the body only when it may move, and never on the charger, in quiet hours or during an alarm).
- A shouted name is a safety notice (`safety/watch.py`): "Did you call me? Is everything okay?", and it goes looking (`Commands.seek_people`).
- "Come to Ina" when Ina isn't here goes to her usual room first (`Commands._find_where_usual`, with `usual_room` from `alive/book.py`: rooms counted per person, fading over weeks).
- Rooms come from furniture (`alive/rooms.py`). Nav drives to a goal through `Navigator.go_to`, under law 1's limits, the motion guard and stop handling.
- The gate (`activities/gate.py`): "come here" and "go to a place" are for friends and up, and children. A stranger gets "come" only when Pebble is in a good mood and curious. Quiet hours, a low battery and resting give a no.

**Planned elsewhere:**
- The household pack: A1 (sounds that matter), A4 (teach a sound, from YAMNet's embeddings), A5 (the chirp detector and finder), A16 (direction, "check first").
- `reports/Model upgrades now non-commercial is allowed.md`: try livekit-wakeword for the name, Silero VAD v6, CED for sound events, Moonshine v2 against NeMo.
- `plans/agency-and-respect-for-life.md` section 6b: ggwave for talking to other bots, with ultrasound off unless the owner switches it on.

**Two facts that matter here:**
- The body's motors are driven at 20 kHz (`firmware/src/config.h`, `PwmHz = 20000`). Pebble's own wheels may sing right inside the band the high-pitch listener watches. That is also a known tone to test with.
- Seen from the front, the phone's top edge is on Pebble's right and its bottom edge (USB-C, with the right-angle power lead in it) on its left (`interfaces.md`). So the top and bottom microphones lie left and right, about 15–16 cm apart on a 163.9 mm phone.

## How it fits together
```
AudioRecord: one feed, as today (the source, rate and channels the probe chose)
 |
 |-- 48 kHz, one to three channels, in a 2 s ring in memory
 |     |-- the band watcher (15 kHz and up): tones and band levels, numbers only
 |     `-- the direction finder (two raw channels): a bearing while a voice or a sound is on
 |
 `-- brought down to 16 kHz mono --> today's listeners, unchanged:
       the speech models in :ears (plus the second listen), the sound tap, YAMNet (plus embeddings)

brain (Python): hearing/highband.py, hearing/habits.py, hearing/direction.py,
                conversation/calls.py (far calls), the caller's trip in activities/
```
If the probe finds nothing better, the feed stays exactly as today, and the parts that need more stay off and say why in `hearingInfo()`.

## A. Measure first
### What is measured
On the real phone, mounted on Pebble at its real height (the eyes are 13–17 cm off the floor), motors off unless a row says otherwise:

| What | How it is scored |
| --- | --- |
| The name | found or not; time after the name ended; false fires an hour |
| Words | word error rate per clip: substitutions, deletions and insertions over the reference words |
| Calls for help | whether the safety code's reader caught them |
| Voice prints | the cosine to the owner's own print, if he has one. The test never makes or changes a print |
| Sounds | YAMNet's score for the right class, and whether it crosses its notice threshold; the beep detector: heard, maybe or not, and seconds to sure |
| The sound itself | speech level and noise level at the phone (dBFS), and the gap between them |
| Direction (if E's check passes) | the bearing found against the true one |
| Cost | processor time per second of sound, for each part |

### Where, and how loud
Normal and raised voice are about 60 and 66 dB(A) at 1 m, ISO 9921's "normal" and "raised" efforts. The TV is on at the household's usual evening volume.

| Spot | Quiet, normal | Quiet, raised | TV on, normal | TV on, raised |
| --- | --- | --- | --- | --- |
| 1 m, straight ahead of the face | yes | yes | | |
| 3 m | yes | yes | yes | yes |
| 5 m | yes | yes | | |
| Next room, about 2 m past the doorway and out of sight, door open | yes | yes | yes | yes |
| The same, door shut | yes | yes | | |

Also:
- two false-fire runs of 30 minutes: the TV on with nobody calling Pebble, and an ordinary evening;
- one row at 3 m while Pebble drives slowly (wheel noise);
- direction rows, if E's check passes: at 3 m from straight ahead, 45° and 90° to each side and behind, 10 calls each, and the doorway's bearing from the next room;
- the check above 15 kHz (C), about 15 minutes.

The tester writes down the straight-line and the walking distance for the next-room spots.

### The material
- **The main reel,** played from a loudspeaker at mouth height (about 1.5 m standing), made by `tools/hearing/reel.py`:
  - 10 calls in Pebble's own synthetic voices (Kitten TTS and Kokoro), slow and low voices included: "Pebble!", "Pebble, come here", "Pebble, can you come to the kitchen?", "Hey Pebble, where are you?" and the like;
  - 5 lines that only sound close ("pebbles on the path", "people", "a pebble in my shoe"), for false fires;
  - 20 LibriSpeech sentences and 20 AMI headset utterances (both CC-BY-4.0, as the existing evaluations used);
  - sounds from `python -m pebble.hearing.fetch --samples` (dog, baby, tap, speech), plus a knock and a doorbell from the household pack's licence-clean set;
  - a stretch of noise to set the level, and a start chirp the phone lines up on.
- **A short safety reel,** played on its own: the real smoke-alarm recording (temporal three), glass, and five calls for help ("Help!", "I've fallen", "I can't get up", ...). The safety ladder stays on throughout. When Pebble asks "Is everything okay?", the tester says "It's fine, it's a test", as with any false alarm.
- **Live:** at each spot and voice level the tester reads a numbered list of 10 calls and 5 sentences in order, one per breath. The phone takes each stretch of speech as the next line.

### The walk
1. **Test mode** (`HEARTEST`, debug build): Pebble listens and scores but doesn't reply, keeps its wheels still (as after a trusted "wait here"), makes and changes no prints, and keeps nothing from the test in its window, gist or diary. The safety ladder stays on.
2. **Set the speaker:** at 1 m, play the level stretch and turn the volume until a phone sound-meter app reads 60 dB(A). Note the step; raised is 6 dB more. Meter apps are rough by a few dB, which doesn't matter: the same speaker and steps are used throughout.
3. **Each cell:** the reel at the cell's level, then the live list at that level. About 6–7 minutes a cell, about 2 hours in all; it can be split over two evenings.
4. The false-fire runs, the driving row, the direction rows and the check above 15 kHz.
5. `adb pull` the numbers file and run `python -m pebble.hearing.far_report`.

### The tools to build
- **`tools/hearing/reel.py`** (PC): makes the reels (48 kHz WAV files) and their manifests (clip times, reference text, sound labels, levels), and prints the licences of everything in them. Reels are made locally from fetched clips and never committed.
- **`HEARTEST`** (Android debug broadcast, beside `HEAR`, `ECHO` and `BARGE`): finds the start chirp on the live feed, then scores every clip against the manifest.
  - It runs shadow pipelines on the same live sound, so one walk compares every candidate with no recording: today's spotter, the spotter with speech-level scaling (B), each clean-up candidate (D) in front of its own recognizer stream, and the direction finder (E).
  - It writes one JSON line per clip to the app's files folder: the clip id, the cell's labels and numbers. Recognised words are scored in memory and dropped, never written.
  - Word error is worked out on the phone, with one text normaliser written in both Python and Kotlin and checked against a shared list of cases.
- **`MICPROBE`** (Android debug broadcast; the same code runs at first start and on "measure again"): the checks in C and E.
- **`python -m pebble.speech.eval`** (PC): the speech evaluations as code at last.
  - LibriSpeech, AMI headset and AMI single distant microphone; the 30 synthetic "Pebble, ..." clips; 30 minutes of meetings for false fires.
  - Far-field copies made in memory with pyroomacoustics: rooms with 0.3–0.7 s of echo, 1–5 m away, two microphones 15.5 cm apart.
  - It scores today's pipeline and every candidate the same way, so the PC can screen candidates before the phone decides.
- **`python -m pebble.hearing.far_report`** (PC): tables by cell and pipeline. `--check` refuses a results file holding anything but numbers, ids and cell labels, so words, paths and sound can't slip into it. The summary tables go into `brain/README.md` ("Hearing" and "Listening and talking"), as numbers only.

### What to expect, before measuring
These are estimates:
- **Distance:** the direct sound falls about 6 dB each time the distance doubles. In a furnished room, after about a metre, the room's echo is as loud as the direct sound. At 3–5 m most of what reaches Pebble is echo, which hurts recognition more than the level does.
- **The next room:** the voice comes round the corner, all echo. A light interior door is typically rated in the low 20s (sound transmission class), so it blocks roughly another 20–25 dB, and the gap under it lets some through.
- **So:** words from another room will be poor (meeting talk from across a table is already 46 % wrong). The name should do better, being one word that people often say loudly and twice. The TV hurts both.
- **YAMNet's thresholds** were set on close recordings, and its scores will drop with distance.

### What the numbers decide
- B's thresholds: what counts as far, and how sure a call is.
- Whether the spotter gets speech-level scaling, or a second, looser spotter stream (B).
- New thresholds for the low notices (knocks, appliances) by distance, checked again on the 30-minute false-alarm runs. The safety notices are only ever made more sensitive, never less, and only if the false-alarm tests still pass.
- Whether a clean-up candidate earns its place (D), and whether the direction finder is good enough to steer by (E).

## B. Called from another room
**What the person gets:** "Pebble!" from the kitchen. Pebble, in the lounge, calls back "Coming!", drives to the kitchen, finds them and says "Yes?". Their next words count as said to it. If it isn't sure the call was for it, it asks "Was that me?" first. If it can't come, it says why, loud enough to be heard.

### Far, and how sure (`conversation/calls.py`)
A call is **far** when nobody in view is speaking (no moving lips, no matched talker) and it arrives well below the room's usual talking level (`LevelMeter.talk_level`), or, once E works, from the direction of a doorway. A's numbers set the thresholds. When in doubt a call is treated as near, which is today's behaviour.

How sure a far call is:
- **Sure:** the spotter found the name and the recognizer's words start or end with it; or the name twice within 10 s; or a "yes" or "come here" after "Was that me?".
- **Unsure:** only one of the spotter and the words; or only a second, looser spotter stream, if A shows one is worth running. The livekit-wakeword spotter the model report plans to try gives a score, which would be the natural "how sure" number.
- **A shout:** a far shout is quiet by the time it reaches the phone. So "shouted" also counts YAMNet's Shout and Yell scores, and a shouted name, a scream or a call for help goes to the safety ladder exactly as today. The far-call path steps aside whenever a safety incident is open.

| Heard | Who (by voice print, with today's bars) | Pebble |
| --- | --- | --- |
| A sure call: the name alone, or "come here" | someone allowed "come here" (friends and up, and children) | "Coming!" in a raised voice, and goes (below) |
| A sure call | a stranger, or a voice it can't match | "I'm here, in the lounge!" It turns towards the sound and goes at most to the door of its own room, and listens |
| A sure question ("Pebble, what time is it?") | anyone allowed to ask it | answers from where it is, in a raised voice, with nothing private |
| An unsure call | anyone | "Was that me?" in a raised voice, then waits 6 s. A yes, the name again or "come here" makes it sure; silence, and it lets it go (noted) |
| Any call in quiet hours | anyone | no driving; a soft "I'm resting. Come and find me if you need me." only if name spotting at night is on |
| Any call when the gate says no (low battery, resting, told to stay) | | the gate's reason, called back: "I'm on my charger and low on battery. Come and find me in the lounge!" |

### Where it goes
The first that applies:
1. A place in the words: "Pebble, come to the kitchen" (rooms it knows, as today).
2. The direction the call came from (E), if it points at a known room or a doorway: a goal about 1 m past that doorway, or the room's middle.
3. The room it last saw the caller in, within the last 10 minutes. This is kept in memory only, never stored.
4. The caller's usual room (`usual_room`, as `_find_where_usual` uses it today).
5. Asking, in a raised voice: "Where are you?" An answer like "the kitchen" goes back to step 1.
6. Otherwise it stays and says "I can't tell where you are. Come and find me!"

At a bathroom or a bedroom it stops at the door and asks "Can I come in?". At a shut door: "The door's shut. I'm just outside!"

### Up close
- On arrival it looks round for the caller: eyes first, then turning.
- When it sees them: "Yes?" or "Here I am!". The conversation marks them attentive for 10 s, so their next words count as said to it.
- Someone else there: "Did you call me?". Nobody: one "Did someone call me?", then up to 2 minutes of looking and listening, then "I couldn't find who called me." and back to what it was doing.
- A second call on the way updates where it is going. "Never mind" or "not you" from the caller ends the trip; a stop stops it.

### The rules it stays inside
- **The trust gate.** A far call becomes the request a near one would be ("come" to the caller), and the gate answers it as today. The one change is stricter: a stranger's far "come" is always a no, whatever Pebble's mood.
- **Who the caller is** comes from the voice print, with today's bars, unchanged. A far voice never updates a print. A far voice that matches nobody counts as a stranger here.
- **Quiet hours:** no driving for a call.
- **Nav's safety:** the trip is an ordinary nav goal, under law 1's speeds and gaps, the motion guard, stop handling, the floor scan and the drop sensor. Pebble never opens a door and never squeezes past one.
- **Alarms first:** no far-call trip starts while an incident is open.
- **Records:** the black box gets `far_call` (how sure, how far, the caller's tier, where it went, how it ended). The mind sees "Ina called you from another room; you went to the kitchen and found her."

### What it reuses
- The name spotter, the addressing cues and `LevelMeter`'s talking level.
- Voice prints and `Speakers.identify`.
- `alive/rooms.py` and `usual_room`.
- `_find_where_usual`'s pattern, as a twin for the caller (`_find_caller`): a "come" to someone out of sight becomes `go_to_place` and then `come`, through the existing chain of requests.
- Nav's `go_to`, `SeekPeople`'s looking round, the gate's "Coming!", and the safety ladder for shouts.

### The spotter and distance
Today the spotter hears the raw sound while the recognizer gets speech scaled towards −23 dBFS, and that scaling is what helped the recognizer most on quiet, far speech. A shadow spotter with the same slow scaling (worked out on speech only, held between, at most 30 times) runs in A's walk. It replaces today's spotter if it finds more far names without more false fires on the TV run.

## C. The high-pitch listener, and listening with patience
### The 48 kHz feed, without breaking today's
- **One `AudioRecord`, as today,** opened at 48 kHz, the rate the hardware runs at. Android gives sound to one ordinary app at a time, and it promises nothing about two captures in one app, so Pebble keeps a single feed.
- **Today's listeners don't change.** A small low-pass filter and every third sample (`Decimate.kt`) make the same 16 kHz mono feed the speech models, the sound tap and YAMNet get now.
- **With two channels,** speech gets one channel (the probe's best), never the plain sum: two microphones 15 cm apart cancel each other at about 1.1 kHz for a voice from the side. Steering them towards the voice is D's higher rung.
- **The 48 kHz sound** goes only to the new parts in the brain's process, in a 2 s ring in memory.
- **The step up is taken only if it loses nothing:** the alarm tests still pass on the brought-down feed, the speech evaluations are no worse, and the echo state is no worse. If the echo canceller won't attach to the new source while "barge on voice" is on, Pebble stays on today's feed.

### What the Pixel really hears above 15 kHz (the check)
Android promises little up there:
- `UNPROCESSED`, if a phone offers it (`PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED`), must stay within ±30 dB of the mid-band from 7 to 22 kHz, with no processing in the path.
- A phone that reports `PROPERTY_SUPPORT_MIC_NEAR_ULTRASOUND` as "true" must hear 18.5–20 kHz no more than 15 dB below 2 kHz, on `VOICE_RECOGNITION` and `UNPROCESSED`. Supporting this is only "strongly recommended".
- A 48 kHz path's own filter cuts off somewhere around 20–22 kHz, and nothing above 24 kHz can be heard at 48 kHz at all. A 96 kHz capture may be accepted but made from 48 kHz sound.

So `MICPROBE` measures it, in three steps:
1. **By itself,** at first start and on "measure again", with no kit:
   - it reads both properties, and each microphone's reported frequency response (`MicrophoneInfo.getFrequencyResponse()`, often empty);
   - it opens each source (`VOICE_RECOGNITION`, `UNPROCESSED`, `MIC`, `CAMCORDER`, `VOICE_COMMUNICATION`) at 16, 48 and 96 kHz, mono and stereo, and records 3 s of the room: the noise in every 1 kHz band up to half the rate. A floor that drops off a cliff at 8 kHz on a 48 kHz feed means the path runs at 16 kHz underneath;
   - it plays a quiet 10–22 kHz sweep from its own speaker. The speakers are weak up there, so this only shows where the path stops;
   - the next time it drives anyway, it looks for its own motors' 20 kHz line. The probe never moves Pebble by itself.

   During the probe every configuration's sound still goes to the alarm listener, so it is never deaf for longer than the moment it takes to switch.
2. **With a tweeter** (owner's answer 21): the PC plays a 96 kHz file through a piezo tweeter at 1 m and then 3 m:
   - steady tones at 15, 16, 17, 17.4, 18, 19, 19.5, 20, 21, 22 and 23 kHz;
   - then 26, 28 and 30 kHz, to see whether anything above 24 kHz folds down into the band (a leaky filter would let it);
   - then a slow sweep.

   For each source and rate the phone reports each tone's level over the room's noise in its own band, and in the band a fold would land in. The tweeter's own output is unknown, so the answer is relative: how far 20 kHz falls below 15 kHz on the same tweeter. An adjustable dog whistle is a second, independent source.
3. **The result,** kept with the phone's other measurements: "this phone hears steady tones up to N kHz on source S at rate R, at least M dB over the room at 1 m", and "folding: yes or no". The band watcher's top is set from it. If nothing above 15 kHz gets through, the high-pitch listener stays off and `hearingInfo()` says "this phone's microphone path stops at N kHz".

### The band watcher (`HighBand.kt`; `hearing/highband.py` is the PC twin)
- **Looking:** every 1,024 samples at 48 kHz (21 ms), a windowed FFT. Its bins are 46.875 Hz apart, the same grid as ggwave's tones. It covers 15 kHz up to the measured top: at most 192 bins.
- **A tone:** each bin keeps its own slow quiet level, as the beep detector does. A tone is a bin standing 12 dB over its quiet level and 8 dB over its neighbours for several frames. Tones are followed as they drift, the way `hearing/alarm.py` follows a beep's pitch.
- **Its shape:**
  - **steady:** 10 s or more within ±50 Hz (chargers, power supplies, some screens);
  - **pulsing:** on and off in a regular rhythm;
  - **sweeping:** the pitch moving steadily, as many repellers do;
  - **data tones:** several tones at once on the 46.875 Hz grid, changing every few tens of milliseconds between 15 and 19.5 kHz (ggwave's ultrasound band);
  - **beacon-like:** short bursts between 18 and 20 kHz, the band in which researchers found tracking beacons being used.
- **Its own tones:** while the wheels turn, the 20 kHz line is Pebble's own and doesn't count. Tones that follow Pebble wherever it is (its own phone) are learned as its own while it sits alone on the dock. Pebble's own voice and sounds mute the watcher, as they mute the alarm listener.
- **What it hands on:** tone events (start, end, pitch, level, shape, how regular) and band levels once a second, numbers only, through `Bridge.highBand(from)`, like `soundScores`.
- **ggwave:** data tones go to ggwave's decoder only if the agency plan's section 6b is built and the owner has switched its ultrasound on. Otherwise Pebble only notes that they are there.
- **Cost:** under 1 % of a small core (est.).

### What Pebble does with it
Owner's answer 16 sets when it speaks up:
- **Asked** "can you hear anything high-pitched?" or "is my charger whining?": "There's a steady tone in here at about 17 kHz. Children and young people can often hear tones that high; most adults can't." "It's loudest near the TV cabinet" needs moving and comparing, like A5's chirp finder (needs nav).
- **Once, by day, to a trusted person,** when a new steady or pulsing tone has been there for 10 minutes. This helps when a child says there is a horrible noise the adults can't hear.
- **Data tones, at most once a day:** "Something in the lounge is sending data tones too high for most people to hear, at about 19 kHz."
- **Honest about reach:** in one lab test of five commercial pest repellers, their loudest frequencies ran from 26 to 80 kHz, above anything a 48 kHz feed hears. Pebble hears only the parts of them that come lower.

### Listening with patience: sound habits (`hearing/habits.py`, extending A4)
Some sounds only mean something over time. Pebble keeps a few numbers about each sound that recurs and notices when it changes.

| Sound | How it is found | What is kept | What Pebble might say |
| --- | --- | --- | --- |
| A fridge or freezer motor cycling | a step in the low band (60–300 Hz), with YAMNet's Hum, Mechanical fan and Mains hum, on and off | the usual run and rest times while it was in earshot | "The fridge motor has been running for two hours without a break. It usually runs about 20 minutes at a time." |
| A dripping tap | sharp little onsets (a 10 ms check on the 16 kHz feed), with YAMNet's Drip, evenly spaced: 20 or more with under 20 % spread | the interval, the room, the days it was heard | "I can hear a drip about every 3 seconds near the bathroom. It was there yesterday too." |
| A smoke alarm's low-battery chirp | A5's detector: one short beep, then a long, even gap | the interval after three chirps, and the days it went on | A5's words: "One of the smoke alarms is chirping about every 40 seconds." |
| A taught sound (A4) | its embeddings, as A4 plans | also its timing (start sound to end tune) and where it is usually heard | "The washing should be done in about 10 minutes." |
| Something new that repeats | a cluster of embeddings heard again and again at an even interval | the cluster and its timing | Once: "There's a beep about every 30 seconds in the kitchen. Do you know what it is?" Then A4 can teach it |

- **YAMNet's embeddings need one change:** `SoundScorer.kt` reads `embeddings` as well as `scores` (the model already makes them), and sends them compactly, as 16-bit numbers, twice a second.
- **Clusters** are cosine matches against at most 64 centres. A frame where speech scores high never joins or makes a cluster.
- **In earshot only:** Pebble moves, so a run that started or ended out of earshot doesn't count towards the usual times.
- **Low notices:** through the ladder like today's baby and water notices, and kept to itself in quiet hours. Never advice and never "it's broken": only what it heard, against what it usually hears.
- **Kept** (owner's answer 18): numbers only, sealed in the self (`hearing/habits.json`). Full detail for 30 days, then only each sound's summary. Forgetting a sound deletes its numbers.
- **A new sound model:** if CED replaces YAMNet (the model report), habits and taught sounds are learned again, because embeddings from different models can't be compared.
- **Cost:** plain code on numbers the phone already makes; under 1 % of a small core (est.).

## D. A clean-up step before speech recognition
### Why carefully
A model that removes noise also leaves small artifacts behind, and recognizers trained on noisy speech often do worse on the cleaned sound than on the raw. A 2022 study found that enhanced speech didn't beat the raw recording for recognition, and that the artifacts, not the leftover noise, were the main cause. Mixing a little of the raw sound back in ("observation adding") recovered much of the gain. Pebble's recognizer (NeMo) learned from many noisy conversations. So the clean-up step is tried where it is most likely to help (far, echoey or noisy speech) and kept only where it measures better.

### The options
sherpa-onnx (already used, Apache-2.0) has streaming denoising for both GTCRN and DPDFNet since version 1.12.30, and its Kotlin API has an `OnlineSpeechDenoiser`. Pebble pins 1.13.8; check that its AAR carries the class.

| Model | Licence | Size | Work per second of sound | Rate | In sherpa-onnx | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| GTCRN | MIT | 48.2K parameters, well under 1 MB | 33 million multiply-adds | 16 kHz | yes, streaming | trained on DNS Challenge 3 and VCTK-DEMAND; the cheapest try |
| DPDFNet baseline, 2, 4, 8 (Ceva) | Apache-2.0 | 2.3–3.5 M parameters; 8.5–14.1 MB | 0.36, 1.35, 2.36 and 4.37 billion | 16 kHz (variants meant for speech recognition) | yes, offline and streaming | DeepFilterNet2 with dual-path blocks; 20 ms windows, 10 ms steps |
| DPDFNet 2 at 48 kHz | Apache-2.0 | 10.3 MB | 2.42 billion | 48 kHz | yes | only with the 48 kHz feed |
| DeepFilterNet 2 and 3 | MIT or Apache-2.0 | about 2 M parameters | DeepFilterNet2 ran at 0.04 of real time on a laptop Core i5 (its authors) | 48 kHz only | no | DPDFNet's baseline is the same family; compared only if DPDFNet disappoints |
| Online WPE (removes echo) | plain code, after nara_wpe (MIT) | none | small: a few taps per frequency | 16 kHz | no | the classic way to remove room echo; much stronger with two channels |
| Steering two microphones (with E) | plain code | none | tiny | 48 kHz | no | points the pair at the voice: up to about 3 dB less noise |

**Phone cost** (estimates, to be measured by the ears' bench): GTCRN about 1–2 % of a small core while it runs. The DPDFNet baseline perhaps a tenth of a big core, or a third to two-thirds of a small one. DPDFNet 2 about four times that.

### How it runs: a second listen (`SherpaEars.kt`)
- **The first listen stays exactly as today,** on the raw sound. Close speech, the name and the speed of replies don't change.
- **A far or noisy turn** (by A's thresholds: the level, the gap between speech and noise, or far by B's test) is cleaned and decoded again: the stretch the engine is already holding goes through the denoiser into a second stream of the same recognizer, so there is no second copy of the model. The better of the two results is kept, by a rule A's numbers choose: the raw one unless the cleaned one is clearly better (the recognizer's own confidence, or always the cleaned one below a given speech-to-noise gap).
- **A far "maybe" name** is checked again on the cleaned stretch too.
- **Time:** about 0.5–1.5 s more, on far or noisy turns only (est.). "Coming!" doesn't wait for it; the words of a far request ("... come to the kitchen") do. If a reply was already being written from the first listen's words (read-ahead, `reports/Cutting response time drastically.md`), the second listen's words count as a revision, like a recognizer revising its words.
- **What stays raw** (owner's answer 20): voice prints, the alarm listener and YAMNet. The safety code reads the first listen's words as today; the second listen can add a reading (a "help" it caught) but never remove one.
- **Privacy:** the stretch is held only while it is being worked on, as today, and dropped when the second listen ends, a few seconds later at most. Nothing is written.

### How it is measured, and when it is switched on
- **PC first** (`pebble.speech.eval`): AMI single distant microphone, AMI headset, LibriSpeech and the far-field copies at 1–5 m. Each candidate is scored with and without a little raw sound mixed back (−6, −10 and −15 dB), on words, names and false fires.
- **Then the phone:** the same candidates as shadow pipelines in A's walk, and their cost under load (the ears' bench: a 10 s far clip while the main model decodes).
- **Switched on** for the second listen only if, on the far and noisy cells, it cuts word errors by at least a tenth, finds no fewer names, adds no false fires on the TV run, and fits its rung's processor cap. Otherwise the step stays off: a step up can never make Pebble worse.
- **A new recognizer** (Moonshine v2, say) means a new evaluation: a denoiser that helps NeMo may hurt another model.

## E. Turning towards a voice
### Does Android give two raw microphones? (check first)
For:
- The Pixel 6 Pro has three identical microphones (Google) and records in stereo (DXOMARK).
- Android can say which microphone feeds which channel, and whether a channel is one microphone's raw sound (`CHANNEL_MAPPING_DIRECT`) or a mix (`CHANNEL_MAPPING_PROCESSED`), through `AudioRecord.getActiveMicrophones()`. `AudioManager.getMicrophones()` gives each microphone's position in metres from the phone's bottom-left-back corner, when the phone fills it in.
- Earlier Pixels were used for two-microphone research: the first Pixel's two microphones, 13 cm apart, captured as two channels.

Against:
- Google says the three microphones aren't all used at once, and that which is used depends on the app.
- Phones often hand over stereo that is already mixed, and a "stereo" voice-recognition feed may be one microphone copied twice.

So `MICPROBE` tries `CHANNEL_IN_STEREO`, and channel index masks of two and three channels, on each source at 48 kHz. It reads the channel mapping and the positions, and then checks for itself: it clicks its own bottom speaker, then its top one. Two real microphones hear each click about half a millisecond apart, the near one first, and the order swaps between the two clicks. A copied channel shows no difference. The delay also gives the spacing (about 15–16 cm) and which channel is which end. Nothing is taken on trust, and nothing is hard-coded.

### Finding the direction (`Direction.kt`; `hearing/direction.py` is the PC twin)
- **The method:** GCC-PHAT, a standard way to find the time difference between two microphones (Knapp and Carter, 1976). The two channels are cross-correlated with every frequency weighted equally, so the peak gives the time difference, interpolated between samples. Frames of 2,048 samples (43 ms) at 48 kHz, half overlapping, only while the voice detector hears speech or a sound event is on.
- **To an angle:** sin(angle) = delay × speed of sound ÷ spacing. The speed of sound is corrected by the air sensor's temperature.
- **The mount suits it:** with the microphones left and right, straight ahead is where both hear the same. The head tilts about that same left-right line, so tilting doesn't change the answer.
- **Front and back** sound the same to two microphones. Pebble turns about 40° and listens again, or looks. A third raw channel (the camera-bar microphone on the back), if Android gives it, may tell front from back by how the phone's body shadows high sounds; that is to try.
- **To the house:** a bearing becomes a world direction through nav's pose, and a goal through nav's map (B's step 2).
- **Cost:** 1–3 % of a small core while a voice is on (est.).

### What accuracy to expect
At 48 kHz one sample of delay is 7 mm of path. With 15.5 cm between the microphones the whole range is about ±22 samples, so near straight ahead one sample is about 2.6°; at 16 kHz it would be about 8°. That is why the 48 kHz feed matters. In practice echo and noise set the error, not the samples. Estimates, which A's direction rows replace:

| Where the voice is | Expected error (est.) |
| --- | --- |
| Same room, quiet, within about 45° of straight ahead | about 5–15° |
| Same room, towards Pebble's left or right side | 15–30° or worse; the angle flattens there |
| Behind | the mirror image of the truth, until it turns |
| TV on | towards the louder of the two |
| Next room | roughly the doorway, where the sound comes in: good enough to drive towards |

### What it is used for
- **Its name, a call for help, a knock, glass or a crash it can't see:** eyes, head, then body towards it (owner's answer 19). `alive.face_sound` is the twin of `face_speaker`, with the same conditions.
- **B's "where the sound came from".**
- **Who is speaking** among the people in view: the voice's bearing is one more cue for `Speakers.talker`.
- **The household pack:** beeping tags and chirps found faster (A5).
- **D's higher rung:** steering the two microphones, and two-channel WPE.

### If the phone gives only one channel
- **For calls,** B's other steps: the words, the room it last saw the caller in, their usual room, and asking "Where are you?".
- **For sounds that go on** (a chirp, a whine, the TV): moving and comparing loudness, as A5's finder does. Slow, but sure.
- **A microphone array on the body** (the household report's C3): not now (owner's answer 22).

## F. Privacy
- **Sound is never recorded or kept.** The 48 kHz sound lives in a 2 s ring in memory, like the sound tap's 10 s today. Nothing is written, on the phone or anywhere.
- **Words** stay in memory for 5 minutes, as today. The second listen works on the stretch the engine already holds, and drops it when it ends.
- **The high-pitch listener keeps numbers only:** tone events and band levels. The sound habits keep timings and YAMNet's embeddings, which describe a second of sound and can't be played back, and never from stretches with speech.
- **Far hearing doesn't change who may command Pebble:** the same gate, the same voice-print bars, no print updates from far voices, no trips into other rooms for strangers, quiet hours unchanged. "Stop listening" stops far listening too; only the name spotter keeps going, as today.
- **What is said in another room stays there.** A far line not said to Pebble is read by the safety code and dropped: it never reaches the window, the gist or the overheard facts (owner's answer 14).
- **Answers carried through the house** say nothing private (owner's answer 13).
- **The measuring** keeps numbers, ids and cell labels only, enforced by `far_report --check`. Recognised words are scored in memory and dropped. The test never makes or changes a print, and keeps nothing in the self.
- **Nothing leaves the phone.** The only exception stays the opt-in notice in words, as today.

## G. The ladder
**Rung 1, the Pixel 6 Pro** (the tested default; every figure is an estimate until measured):

| Part | Pixel 6 Pro rung | Processor | Memory |
| --- | --- | --- | --- |
| The feed | 48 kHz, one or two channels, if the probe finds a feed that loses nothing; otherwise today's 16 kHz | bringing it down: under 0.5 % of a small core | a 2 s ring, under 0.5 MB |
| Band watcher | 15 kHz to the measured top, 47 looks a second | under 1 % of a small core | — |
| Sound habits | plain code on YAMNet's numbers, and a 10 ms onset check | under 1 % | a few hundred kB in the self |
| Far calls | plain code; the spotter with speech-level scaling, if A shows it helps | — | — |
| Direction | GCC-PHAT on two raw channels while a voice is on | 1–3 % of a small core while on | — |
| Clean-up | the second listen, on far or noisy turns only, with GTCRN, or the DPDFNet baseline if it wins and fits | GTCRN 1–2 % of a small core while running; the DPDFNet baseline about a tenth of a big core | up to 10 MB |

**Higher rungs,** only when the phone measures fast enough:

| Rung | What steps up | Switches on when |
| --- | --- | --- |
| 2 | DPDFNet 2 on the second listen; steering the two microphones and two-channel WPE before it; a second, looser spotter stream, if A showed it finds far names | the denoiser runs under 0.3 of real time on the core it gets while the main model decodes, at thermal "none" or "light" |
| 3 | DPDFNet 2 or 4 in front of the recognizer on every turn, not only far ones; DPDFNet at 48 kHz on the 48 kHz feed; three channels for front and back | under 0.15 of a core in front of every turn, with close speech no worse on the evaluations |

- **Measuring:** `MICPROBE` at first start and on "measure again" (a few minutes: up to about 60 source, rate and channel settings at 3 s each, most of which a phone refuses at once); the ears' bench times each denoiser on a 10 s far clip under load.
- **Stepping down:** three slow turns in a row, thermal "moderate" or an error drops the clean-up a rung; at "severe" it stops. The band watcher and direction are too cheap to matter.
- **The last rung is today's feed.** A feed problem (a read error, Android silencing the capture, the echo canceller lost while "barge on voice" is on) puts the microphone back on today's 16 kHz feed.

## H. Seams and where the code goes
**Android** (`android/app/src/main/java/nz/pebble/robot/brain/`):
- `Microphone.kt`: a `MicPlan` (source, rate, channels, which channel feeds speech), chosen by the probe and remembered like `LlamaChoice` (a step down after a failure); a `WideSink` for 48 kHz listeners beside today's `AudioSink`, which keeps getting 16 kHz mono. Test audio gains 48 kHz and stereo WAV files, so the new parts can be checked on the emulator.
- New: `Decimate.kt`, `MicProbe.kt`, `HighBand.kt`, `Direction.kt`.
- `SoundScorer.kt`: `embeddings` as well as `scores`.
- `SherpaEars.kt`: the spotter's speech-level scaling (a setting), the second listen with `OnlineSpeechDenoiser`, and the new event fields.
- `Speech.kt`: a raised-voice part flag beside `whisper`.
- `Bridge.kt`: `highBand(from)`, `soundBearings(from)`, `micPlan()`.
- Debug: `MICPROBE` and `HEARTEST` in `DebugBrain.kt`, beside `HEAR` and `ECHO`.

**Speech events** (`brain/pebble/speech/events.py`):
- `keyword` and `final` gain `far` (true, false or unknown), the level against the room's talking level, and `bearing_deg` when known;
- a new `second` event carries the second listen's words for a segment.

**Brain** (`brain/pebble/`):
- `hearing/highband.py`, `hearing/direction.py`, `hearing/habits.py` (with A4's taught sounds) and `hearing/far_report.py`;
- `conversation/calls.py`: far or near, how sure, what to say and where to go; far lines not said to Pebble go to safety and nowhere else;
- `activities/commands.py`: `_find_caller`, the twin of `_find_where_usual`; `activities/gate.py`: a `far` field on the situation, so a stranger's far "come" is a no;
- `alive/core.py`: `face_sound(bearing)`;
- `safety/watch.py`: a far shout also counts YAMNet's Shout and Yell; the ladder's people-finding gets the bearing when there is one;
- `speech/eval.py`: the evaluations as code.

**Tools:** `tools/hearing/reel.py`; fixtures shared by the Python and Kotlin twins (decimation, the band watcher, GCC-PHAT, the text normaliser) from `android/tools/hearing_fixtures.py`, as the eyes' fixtures are made.

**Who builds it:** pebble-android (the feed, the probes, the Kotlin parts, `:ears`), pebble-talk (far calls, the words, the second listen's use), pebble-commands (the gate and the caller's trip), pebble-nav (the bearing goal), pebble-safety (the shout cue, and the alarm tests on the new feed).

## I. The sim, tests and evaluation
**Sim:**
- A two-room house from nav's sim buildings, with walls and a doorway. A voice reaching Pebble is scaled by distance and by each wall or door between them (`hearing/synth.py`'s `muffle`), and comes from the doorway's bearing when the speaker is out of sight.
- Sim speech events carry `far`, the level and the bearing.
- `python -m pebble.sim.call_scene`: Ina calls from the kitchen; Pebble calls back "Coming!", drives through the doorway and says "Yes?", and she asks it something. A voice it doesn't know calls from the hallway: "I'm here, in the lounge!", and no trip. At 23:00, no trip. The TV says "pebble": nothing.

**Tests**, written first:
- **Far calls:**
  - a sure call from a trusted voice goes to the caller's room and ends with the caller attentive;
  - an unsure call asks "Was that me?" and moves only after a yes, at most three times an hour;
  - a stranger or an unmatched voice never takes Pebble out of its room;
  - no trip in quiet hours, during an alarm, on a low battery or after "wait here";
  - a stop stops the trip;
  - a shouted name goes to the safety ladder and doesn't also start a far call;
  - a far voice never updates a print;
  - bathroom and bedroom doors get "Can I come in?".
- **Privacy:**
  - a far line not said to Pebble reaches the safety code and nothing else (window, gist, overheard facts);
  - a raised far answer never carries an overheard fact;
  - `far_report --check` refuses a file with words in it;
  - no new part writes sound.
- **The feed:**
  - bringing 48 kHz down to 16 kHz keeps folded sound at least 60 dB down;
  - every alarm test passes on 48 kHz sound brought down to 16 kHz;
  - with no better feed, everything is as today and `hearingInfo()` says why.
- **High band:**
  - made-up 48 kHz tones (a steady 17.4 kHz, a pulsing one, a sweep, ggwave-like hops, beacon bursts) are found and named;
  - speech and music give no tones;
  - the 20 kHz motor line while driving counts as Pebble's own;
  - a path that stops at 8 kHz switches the watcher off.
- **Habits:**
  - made-up fridge cycles are learned, and one long run is mentioned once;
  - even drips are found and uneven clicks aren't;
  - a chirp's interval comes out after three chirps;
  - frames with speech never make a cluster;
  - forgetting deletes, and full detail is thinned after 30 days.
- **Direction:**
  - two made-up channels with a known delay, and pyroomacoustics rooms, give bearings within the expected errors;
  - behind stays unsure until a turn;
  - the speaker clicks give the spacing and which channel is which end.
- **Clean-up:** close speech decodes exactly as before, because the first listen is untouched; the second listen never removes a safety reading.
- **Kotlin and Python agree** on the shared fixtures, as the eyes' twins do.

**Evaluation:** `pebble.speech.eval` on the PC and A's walk on the phone. Targets, checked once on the walk:
- from the next room with the door open, at a raised voice, the name found in at least 8 of 10 calls;
- no far-call trip in 30 minutes of TV, and at most one "Was that me?" an hour on an ordinary evening;
- steady high tones found within 2 s at 10 dB over the high band's quiet level;
- direction within 15° (median) within 45° of straight ahead at 3 m;
- the clean-up step's own test in D.

## Honest limits
- **Nothing here has run on the phone.** Every distance, speed and accuracy is an estimate until the walk.
- **From another room** whole sentences will often be misheard; the name and short calls are what can work. A shut door may stop even those.
- **Many far callers will be "a voice I can't match".** Prints are weak at a distance and the bar isn't lowered, so Pebble will often answer from where it is rather than come.
- **It is slow:** at 0.25–0.3 m/s it takes 30–60 s to reach another room, and it can't open doors.
- **The TV talks too.** Its voices are unknown voices, and its sound can hide a call.
- **Above 20 kHz the phone probably hears little,** and above 24 kHz nothing at 48 kHz. Most pest repellers are out of reach.
- **Direction is rough,** front and back need a turn, and from the next room it points at the doorway, not the person.
- **Cleaning speech may not help this recognizer at all.** Then the step stays off.
- **Its own noises:** Pebble's wheels sing at 20 kHz and its phone may whine. It learns those, but while driving it can miss a real tone at the same pitch.
- **The microphone holes must be open:** the top edge, the bottom edge beside the USB-C port (where the right-angle power lead plugs in) and the camera bar. Check the case and the mount on the real phone before the walk; a blocked hole quietly spoils every number here.
- **Pebble only hears where Pebble is.** There are no microphones in other rooms.
- **It is not a hearing aid, a pest-repeller tester or a leak detector.** The habits only say what it heard, against what it usually hears.

## Licences of the new parts
| Part | Licence | Use it? |
| --- | --- | --- |
| GTCRN (code and checkpoints) | MIT | Yes |
| DPDFNet (Ceva) | Apache-2.0 | Yes |
| DeepFilterNet 2 and 3 | MIT or Apache-2.0 | Only if DPDFNet disappoints |
| sherpa-onnx's `OnlineSpeechDenoiser` | Apache-2.0 (already used) | Yes |
| Online WPE, GCC-PHAT, the band watcher, decimation | plain code written here (WPE after nara_wpe, MIT) | Yes |
| pyroomacoustics (PC tests only) | MIT | Yes, as a development package |
| ggwave (the hand-off for data tones; already planned in the agency plan) | MIT | Yes |
| Evaluation clips: LibriSpeech and AMI | CC-BY-4.0 | Fetched, never committed; credited in the report tool's output |
| Test sounds already in `hearing/fetch.py` | CC0, CC BY 4.0, public domain | Fetched, never committed |
| Synthetic calls in Pebble's own voices (Kitten TTS; Kokoro with espeak-ng) | Apache-2.0; espeak-ng GPL-3.0 (already listed) | Made on the PC, never committed |

Nothing new is non-commercial or copyleft, so NOTES.md's "Licences of the parts" gains no line. Each model's own licence file is fetched and shipped with it, as `YAMNET_LICENSE` is.

## Still open
Kept open because the recommended answer would loosen a privacy or trust rule:
1. **Re-recordings of the public test clips** (privacy). Keeping the phone's own recording of the reel (public clips played from a speaker, nobody meant to be talking) on the PC, outside the repo, would let a new model be scored later without walking the house again. But it records sound in the house, which today's rule forbids, and a recording can catch someone talking in the background.
   - *Recommended:* yes, only in a debug build, only in a session the owner starts, only the reel's own time slots, on the PC outside the repo, deleted after 30 days.
   - Until answered, everything is scored live on the phone, as A describes.
2. **A spoken name for a far caller Pebble can't recognise** ("Pebble, it's Ina, come here!") (trust). This is NOTES.md's open "someone spoofing a spoken name".
   - *Recommended:* a spoken name alone never sends Pebble into another room; it says "Come and find me in the lounge!".
   - Until answered, a spoken name doesn't count, as today.

Decided in NOTES.md on 20 October 2026 and built the same day (brain README "What it hears" and "Very responsive when talked to"): name spotting at night is on (its name wakes words for 30 s, and it whispers), and Pebble stops talking on any voice, telling its own voice apart by the echo check and the ears' own-voice mark. So answer 7 and the quiet-hours row above apply once far calls are built: a far call at night gets the soft "I'm resting" line.

## Build order
**Where it fits:** the household pack, right after Android round 3 (CLAUDE.md, work order 2.2). Within the pack it comes after A1 and A4, because the sound habits extend A4, and it brings A16.

**What needs the phone first:** item 1, all of it, and the "check first" halves of item 3 (how high the phone hears) and item 5 (whether it gives two raw channels). Items 2 and 4 can be built in the sim and on the PC first, and wait for the phone only for their thresholds and the switch-on.

1. **PC tools and seams:** `pebble.speech.eval`, `tools/hearing/reel.py`, `far_report` with `--check`; the seams, the sim stand-ins and the tests, written first. No phone needed.
2. **On the phone, `MICPROBE`** and its self-checks, after checking that the case and mount leave the microphone holes open. This answers the "check first" for items 3 and 5.
3. **On the phone, the walk** (`HEARTEST`) with today's pipeline and the shadows. The baseline tables go into `brain/README.md`.
4. **Called from another room** (item 2): the sim first, then the phone with the walk's thresholds, and the spotter's scaling if the walk says so.
5. **The 48 kHz feed** and bringing it down, if the probe found a feed that loses nothing. No behaviour changes; the alarm tests and evaluations run again.
6. **The high-pitch listener** (item 3), if the probe saw anything above 15 kHz: on the PC with made-up tones, then the tweeter check; then the sound habits, with A4 and A5.
7. **Turning towards a voice** (item 5), if the probe found two raw channels: GCC-PHAT, `face_sound`, B's direction step, and the walk's direction rows.
8. **The clean-up step** (item 4): screened on the PC, then the phone's shadows; switched on only where it measures better. Steering the two microphones and WPE, if item 5 works.
9. **Measure again,** end to end. Then the README sections ("Hearing", "Listening and talking") and the two still-open questions in NOTES.md's list of open decisions.

## Sources
- Android microphones and sources: [MicrophoneInfo](https://developer.android.com/reference/android/media/MicrophoneInfo) and its [source, for the position's origin and the channel mappings](https://github.com/aosp-mirror/platform_frameworks_base/blob/master/media/java/android/media/MicrophoneInfo.java); [AudioRecord (`getActiveMicrophones`)](https://developer.android.com/reference/android/media/AudioRecord); [AudioManager (`getMicrophones`, the unprocessed and near-ultrasound properties)](https://developer.android.com/reference/android/media/AudioManager); [MediaRecorder.AudioSource (`UNPROCESSED`)](https://developer.android.com/reference/android/media/MediaRecorder.AudioSource); [AudioFormat (channel masks and index masks)](https://developer.android.com/reference/android/media/AudioFormat); [sharing audio input](https://developer.android.com/media/platform/sharing-audio-input)
- Android's compatibility rules: [CDD, Android 16](https://source.android.com/docs/compatibility/16/android-16-cdd); [section 5.11, unprocessed capture (a mirror of the CDD source)](https://os.unplugged.com/werunplugged/unplugged-vendor/raw/branch/main/compatibility/cdd/5_multimedia/5_11_unprocessed-audio.md); [section 7.8.3, near-ultrasound (same mirror)](https://os.unplugged.com/werunplugged/unplugged-vendor/raw/branch/main/compatibility/cdd/7_hardware-compatibility/7_8_audio.md); [the CDD change on near-ultrasound and resampling](https://android.googlesource.com/platform/docs/source.android.com/+/20cdbb7%5E%21); [near-ultrasound tests](https://source.android.com/docs/compatibility/cts/near-ultrasound)
- The Pixel's microphones: [Google, Pixel speakers and microphones](https://support.google.com/pixelphone/answer/14748890); [DXOMARK, Pixel 6 Pro audio](https://www.dxomark.com/google-pixel-6-pro-audio-review); the first Pixel's two microphones 13 cm apart: [two-microphone speech separation on a smartphone (arXiv 1812.03914)](https://arxiv.org/abs/1812.03914); [UT Dallas SSPRL, direction-finding demos on Google Pixel](https://labs.utdallas.edu/ssprl/hearing-aid-project/video-demonstration)
- Clean-up models: [GTCRN](https://github.com/Xiaobin-Rong/gtcrn) and [its licence](https://github.com/Xiaobin-Rong/gtcrn/blob/main/LICENSE); [DPDFNet model card](https://huggingface.co/Ceva-IP/DPDFNet) and [paper](https://arxiv.org/abs/2512.16420); [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) and [DeepFilterNet2 paper](https://arxiv.org/abs/2205.05474); [sherpa-onnx speech enhancement](https://k2-fsa.github.io/sherpa/onnx/speech-enhancement/index.html), [its model release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speech-enhancement-models), [`OnlineSpeechDenoiser.kt`](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/kotlin-api/OnlineSpeechDenoiser.kt) and [CHANGELOG](https://github.com/k2-fsa/sherpa-onnx/blob/master/CHANGELOG.md); [nara_wpe](https://github.com/fgnt/nara_wpe)
- Cleaning can hurt recognition: [Iwamoto and others, How bad are artifacts? (Interspeech 2022)](https://arxiv.org/abs/2201.06685)
- High sounds: [ggwave (ultrasound protocols from 15 kHz, 46.875 Hz apart)](https://github.com/ggerganov/ggwave); [The Mosquito (about 17.4 kHz)](https://en.wikipedia.org/wiki/The_Mosquito); [Arp and others, ultrasonic beacons on Android, 18–20 kHz (EuroS&P 2017)](https://vamos.mlsec.org/docs/2017a-eurosp.pdf); [SoniControl, detecting them on a phone](https://arxiv.org/abs/1807.07617); [lab test of five commercial ultrasonic repellers, peaks 26–80 kHz](https://esa.confex.com/esa/2001/techprogram/paper_3118.htm)
- Voice levels and doors: ISO 9921 vocal effort at 1 m, [as tabled in a course handout](https://www.f5kav.fr/wp-content/uploads/simple-file-list/F5RCT/Realisations/Squirrely/Support/intelligible1.pdf) and [used in a 2013 study](https://doaj.org/article/26070127a3e2473295f8c2555fe85eca); hollow-core doors in the low 20s: [a buying guide](https://www.hometips.com/buying-guides/sound-blocking-doors.html), [a field test](https://commercial-acoustics.com/case-studies/door-flanking-demising-walls-stc-test/)
- Direction: [Knapp and Carter, the generalized correlation method (1976)](https://doi.org/10.1109/TASSP.1976.1162830); [pyroomacoustics](https://github.com/LCAV/pyroomacoustics)
- In this repo: `reports/More everyday value for the household.md` (A1, A4, A5, A16, C3 and the owner's answers), `reports/Model upgrades now non-commercial is allowed.md` (spotter, VAD, sound-model and recognizer tries), `reports/Cutting response time drastically.md` (read-ahead), `plans/agency-and-respect-for-life.md` section 6b (ggwave), `brain/README.md` ("Hearing", "Listening and talking"), `android/README.md` ("The ears and the voice"), `interfaces.md` (the phone mount), `firmware/src/config.h` (the 20 kHz motor drive)
